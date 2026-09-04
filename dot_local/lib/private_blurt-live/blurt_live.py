"""Live (streaming) OpenAI transcription for blurt, with local fallback.

Why streaming and not the file endpoint: blurt's wait is dominated by sending
and processing audio *after* you stop talking. A realtime session sends audio
while you talk, so only the tail costs anything. Measured end to end on this machine through the real daemon and socket, 25 s
clip: local faster-whisper 18-22 s, this path 1.08 s after key release (tail
commit->text 0.79 s). Model comparison at 25 s, median of 4: gpt-live-transcribe
0.88 s (60 incremental deltas), gpt-transcribe 1.51 s (0 deltas -- it waits for
the commit), gpt-realtime-whisper delay=minimal 0.64 s but emitted only half the
text, so it is not the safe default.

blurt is a pacman package (/usr/lib/blurt); editing it there is clobbered on
upgrade. So this module lives outside it, patches three names at import time,
and calls the stock entry point. Nothing under /usr/lib is touched.

  Recorder.start    -> also open a realtime session (overlaps your speech)
  Recorder._callback-> also tee frames to that session
  Recorder.stop     -> also commit the buffer
  WhisperModel      -> proxy: return the streamed text, else run local whisper

Everything else in blurt is untouched: clipboard, type_text, submit/Enter,
timing history, progress bar, the live VAD meter, error reporting.

Wire it with a systemd user drop-in:
    ExecStart=
    ExecStart=/usr/bin/python3 -m blurt_live
    Environment=PYTHONPATH=/usr/lib/blurt:%h/.local/lib/blurt-live

Self-check (no network, no key needed):   python3 -m blurt_live --check
Live check against a wav:                 python3 -m blurt_live --live FILE.wav
"""

import asyncio
import base64
import json
import os

import sys
import threading
import time
import types

import numpy as np

from blurt import config as C
from blurt import daemon as D

_REAL_WHISPER = D.WhisperModel        # capture before we shadow the name

WS_URL = os.environ.get("BLURT_LIVE_URL", "wss://api.openai.com/v1/realtime")
MODEL = os.environ.get("BLURT_LIVE_MODEL", "gpt-live-transcribe")
WIRE_RATE = 24000                     # API rejects < 24000; measured, not assumed
CHUNK_MS = 200                         # OpenAI's recommended append size
# Budget for the tail (commit -> completed). Measured 0.7-1.3 s; 15 s is a
# generous ceiling that still fails over to local instead of hanging forever.
RESULT_TIMEOUT = float(os.environ.get("BLURT_LIVE_TIMEOUT", "15"))
# FR+EN both, mixed inside one sentence. Order is not a priority ranking.
LANGUAGES = [x for x in os.environ.get("BLURT_LIVE_LANGS", "fr,en").split(",") if x]
# Hard cap on how much audio one session may stream. This is a COST fuse, not a
# quality knob: blurt has wedged before and recorded for 14 hours straight (the
# journal has a 51360 s clip), which on a per-minute API is real money. Longest
# genuine dictation on record is 75 s, so 300 s is far above normal use. Past the
# cap the session aborts and the local model handles it, free.
MAX_STREAM_SECONDS = float(os.environ.get("BLURT_LIVE_MAX_SECONDS", "300"))
KEY_FILE = os.path.join(C.CONFIG_DIR, "openai.key")


def api_key():
    """Key from env, else ~/.config/blurt/openai.key. Raises if unusable.

    Refuses a key file readable by group/other: a leaked key is worse than a
    slow transcription, and every caller falls back to the local model anyway.
    """
    for var in ("BLURT_LIVE_KEY", "OPENAI_API_KEY"):
        k = os.environ.get(var)
        if k and k.strip():
            return k.strip()
    mode = os.stat(KEY_FILE).st_mode          # FileNotFoundError -> fallback
    if mode & 0o077:
        raise PermissionError(
            f"{KEY_FILE} is group/world readable ({mode & 0o777:o}); chmod 600")
    with open(KEY_FILE) as f:
        k = f.read().strip()
    if not k:
        raise ValueError(f"{KEY_FILE} is empty")
    return k


class Resampler:
    """Stateful 16 kHz -> 24 kHz for a stream arriving in arbitrary-size chunks.

    resample_poly() on each chunk independently would put a filter transient at
    every chunk edge (5x/second), which lands in the audio the model scores. So
    keep PAD input samples of history on each side and emit only the steady
    middle. Output is exact and gap-free; the cost is PAD samples of latency.
    """

    PAD = 96                                 # input samples of context per side

    def __init__(self, src=C.SAMPLE_RATE, dst=WIRE_RATE):
        from math import gcd
        g = gcd(src, dst)
        self.up, self.down = dst // g, src // g
        self._buf = np.zeros(0, dtype=np.float32)
        self._primed = False

    def push(self, x):
        """-> float32 resampled samples for this chunk (may be empty)."""
        from scipy.signal import resample_poly
        self._buf = np.concatenate([self._buf, np.asarray(x, dtype=np.float32)])
        # Need history on both sides before we can emit a clean middle.
        if self._buf.size < 2 * self.PAD + self.down:
            return np.zeros(0, dtype=np.float32)
        usable = self._buf.size - self.PAD                  # keep a right tail
        usable -= usable % self.down                        # whole output frames
        if usable <= self.PAD:
            return np.zeros(0, dtype=np.float32)
        y = resample_poly(self._buf[:usable + self.PAD], self.up, self.down)
        lead = 0 if not self._primed else self.PAD * self.up // self.down
        keep_to = usable * self.up // self.down
        self._primed = True
        self._buf = self._buf[usable - self.PAD:]
        return y[lead:keep_to].astype(np.float32)

    def flush(self):
        """-> the final tail, including the right edge."""
        from scipy.signal import resample_poly
        if self._buf.size == 0:
            return np.zeros(0, dtype=np.float32)
        y = resample_poly(self._buf, self.up, self.down)
        lead = self.PAD * self.up // self.down if self._primed else 0
        self._buf = np.zeros(0, dtype=np.float32)
        return y[lead:].astype(np.float32)


def _pcm16(x):
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def _bias():
    """Vocabulary bias for the session, from blurt's existing `prompt` config.

    Two mechanisms, deliberately both:
      keywords[] - documented literal-term biasing for gpt-live-transcribe. It
        cannot act as a decoder prefix, so it cannot drag FR audio into EN. The
        API accepts it but does NOT echo it in session.updated, so we can't
        confirm it applies -- hence the belt-and-braces prompt below.
      prompt     - the string blurt already uses as Whisper's initial_prompt. It
        IS a decoder prefix, so in principle it can bias output language. Low
        risk here because the value is a bare term list, not English prose.
        Set BLURT_LIVE_PROMPT=0 to drop it if EN ever bleeds into FR output.
    """
    raw = (C.PROMPT or "").strip()
    if not raw:
        return {}
    out = {}
    terms = [t.strip(" .") for t in raw.split(",")]
    terms = [t for t in terms if t]
    if terms:
        out["keywords"] = terms
    if os.environ.get("BLURT_LIVE_PROMPT", "1") not in ("0", "false", "no"):
        out["prompt"] = raw
    return out


class LiveSession:
    """One realtime transcription session, driven from a background thread.

    The audio callback must never block, so feed() only does queue.put(). All
    network work happens on this object's own event loop thread.
    """

    _SENTINEL = object()

    def __init__(self):
        # Loop and queue are built here, synchronously, so feed() can never race
        # a not-yet-started thread. call_soon_threadsafe() before the loop runs
        # just queues the callback.
        self._loop = asyncio.new_event_loop()
        self._aq = asyncio.Queue()
        self._text = None
        self._error = None
        self._done = threading.Event()
        self._aborted = False
        self._t_commit = None
        self.t_result = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # --- called from the daemon / audio callback ---------------------------
    def _post(self, item):
        """Hand an item to the loop thread. Never blocks, never raises."""
        try:
            self._loop.call_soon_threadsafe(self._aq.put_nowait, item)
        except RuntimeError:
            pass                              # loop already closed

    def feed(self, mono_float32):
        if not self._done.is_set():
            self._post(np.asarray(mono_float32, dtype=np.float32).copy())

    def commit(self):
        self._t_commit = time.time()
        self._post(self._SENTINEL)

    def abort(self):
        """Discard: stop the session without asking for a transcript."""
        self._aborted = True
        self._post(self._SENTINEL)
        self._done.set()

    def result(self, timeout=RESULT_TIMEOUT):
        """-> transcript str. Raises if the session failed; caller falls back."""
        if not self._done.wait(timeout):
            raise TimeoutError(f"no transcript within {timeout}s")
        if self._error:
            raise self._error
        if self._text is None:
            raise RuntimeError("session produced no transcript")
        return self._text

    # --- background thread -------------------------------------------------
    def _run(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        except Exception as e:                # noqa: BLE001 - surfaced via result()
            self._error = e
        finally:
            self._done.set()
            try:
                self._loop.close()
            except Exception:                 # noqa: BLE001
                pass

    async def _session(self):
        import aiohttp
        key = api_key()                       # raises -> local fallback
        cfg = {"model": MODEL, **_bias()}
        lang = C.whisper_language()
        if lang:
            cfg["language"] = lang
        else:
            # No pin. This user mixes FR and EN inside single sentences, so
            # declare both rather than pinning one or letting it guess from 99.
            cfg["languages"] = LANGUAGES

        async with aiohttp.ClientSession() as sess:
            async with sess.ws_connect(
                WS_URL, headers={"Authorization": f"Bearer {key}"},
                params={"intent": "transcription"}, max_msg_size=0, heartbeat=20,
            ) as ws:
                await ws.send_json({
                    "type": "session.update",
                    "session": {"type": "transcription", "audio": {"input": {
                        "format": {"type": "audio/pcm", "rate": WIRE_RATE},
                        "transcription": cfg,
                        "turn_detection": None,
                    }}},
                })
                await self._await_event(ws, "session.updated", timeout=20)
                sender = asyncio.create_task(self._pump(ws))
                try:
                    await self._collect(ws)
                finally:
                    sender.cancel()

    async def _await_event(self, ws, want, timeout):
        import aiohttp
        while True:
            msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
            if msg.type is not aiohttp.WSMsgType.TEXT:
                raise ConnectionError(f"websocket closed during handshake: {msg.type}")
            ev = json.loads(msg.data)
            if ev.get("type") == want:
                return ev
            if ev.get("type") == "error":
                raise RuntimeError(f"api error: {ev.get('error')}")

    async def _pump(self, ws):
        """Drain the audio queue -> resample -> base64 -> append events."""
        rs = Resampler()
        pending = np.zeros(0, dtype=np.float32)
        step = int(WIRE_RATE * CHUNK_MS / 1000)
        sent = 0                              # wire samples, for the cost fuse
        while True:
            item = await self._aq.get()
            if item is self._SENTINEL:
                pending = np.concatenate([pending, rs.flush()])
                if pending.size and not self._aborted:
                    await ws.send_json({"type": "input_audio_buffer.append",
                                        "audio": base64.b64encode(_pcm16(pending)).decode()})
                if not self._aborted:
                    await ws.send_json({"type": "input_audio_buffer.commit"})
                return
            pending = np.concatenate([pending, rs.push(item)])
            while pending.size >= step:
                await ws.send_json({"type": "input_audio_buffer.append",
                                    "audio": base64.b64encode(_pcm16(pending[:step])).decode()})
                pending = pending[step:]
                sent += step
                if sent / WIRE_RATE > MAX_STREAM_SECONDS:
                    self._aborted = True
                    self._error = RuntimeError(
                        f"exceeded {MAX_STREAM_SECONDS:.0f}s stream cap "
                        f"(recording likely wedged); not billing further")
                    print(f"[blurt-live] {self._error}", file=sys.stderr, flush=True)
                    return

    async def _collect(self, ws):
        import aiohttp
        parts = []
        while True:
            msg = await asyncio.wait_for(ws.receive(), timeout=RESULT_TIMEOUT + 30)
            if msg.type is not aiohttp.WSMsgType.TEXT:
                raise ConnectionError(f"websocket closed: {msg.type}")
            ev = json.loads(msg.data)
            kind = ev.get("type", "")
            if kind.endswith("input_audio_transcription.delta"):
                parts.append(ev.get("delta", ""))
            elif kind.endswith("input_audio_transcription.completed"):
                self._text = (ev.get("transcript") or "".join(parts)).strip()
                if self._t_commit:
                    self.t_result = time.time() - self._t_commit
                return
            elif kind == "error":
                raise RuntimeError(f"api error: {ev.get('error')}")


class LiveModel:
    """Stand-in for faster_whisper.WhisperModel.

    transcribe() returns the text the live session already streamed. On any
    failure it runs the real local model instead, so speech is never lost. The
    local model is built lazily: a setup that never fails never pays its RAM.
    """

    def __init__(self, *a, **kw):
        self._args, self._kwargs = a, kw
        self._local = None
        self._lock = threading.Lock()

    def _fallback(self):
        with self._lock:
            if self._local is None:
                print("[blurt-live] loading local model for fallback ...", flush=True)
                self._local = _REAL_WHISPER(*self._args, **self._kwargs)
        return self._local

    def transcribe(self, audio, **kw):
        audio = np.asarray(audio)
        # blurt warms the model on np.zeros() at startup; never call out for that.
        if audio.size == 0 or not np.any(audio):
            return [], types.SimpleNamespace(language=None, language_probability=None)

        sess = _take_session()
        if sess is not None:
            try:
                text = sess.result()
                tail = f" (tail {sess.t_result:.2f}s)" if sess.t_result else ""
                print(f"[blurt-live] streamed{tail}", flush=True)
                return ([types.SimpleNamespace(text=text)],
                        types.SimpleNamespace(language=None, language_probability=None))
            except Exception as e:               # noqa: BLE001
                print(f"[blurt-live] live session failed ({e}); using local model",
                      file=sys.stderr, flush=True)
        return self._fallback().transcribe(audio, **kw)


# --- session handoff between Recorder and LiveModel -------------------------
_current = None
_current_lock = threading.Lock()


def _take_session():
    global _current
    with _current_lock:
        s, _current = _current, None
        return s


def _set_session(s):
    global _current
    with _current_lock:
        old, _current = _current, s
    if old is not None:
        old.abort()


def install():
    """Patch blurt in memory. Idempotent."""
    if getattr(D, "_live_installed", False):
        return
    D.WhisperModel = LiveModel

    R = D.Recorder
    real_start, real_cb, real_stop = R.start, R._callback, R.stop

    def start(self):
        ok = real_start(self)
        if ok:
            try:
                _set_session(LiveSession())      # connects while you speak
            except Exception as e:               # noqa: BLE001
                print(f"[blurt-live] could not open session ({e}); local this time",
                      file=sys.stderr, flush=True)
                _set_session(None)
        return ok

    def _callback(self, indata, frames, time_info, status):
        real_cb(self, indata, frames, time_info, status)
        if self.recording:
            s = _current                         # plain read; feed() is cheap
            if s is not None:
                s.feed(indata[:, 0] if indata.ndim > 1 else indata)

    def stop(self):
        audio = real_stop(self)
        s = _current
        if s is not None:
            s.commit()
        return audio

    R.start, R._callback, R.stop = start, _callback, stop

    real_cancel = D.Daemon.cancel_recording

    def cancel_recording(self):
        real_cancel(self)
        s = _take_session()                      # discard: no commit, no bill
        if s is not None:
            s.abort()

    D.Daemon.cancel_recording = cancel_recording
    D._live_installed = True


# --- checks -----------------------------------------------------------------
def _check():
    """Offline self-check: the resampler and the wire encoding."""
    rs = Resampler()
    sr, dst = C.SAMPLE_RATE, WIRE_RATE
    t = np.arange(3 * sr) / sr
    x = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    out = [rs.push(x[i:i + 512]) for i in range(0, x.size, 512)]
    out.append(rs.flush())
    y = np.concatenate(out)

    want = int(round(x.size * dst / sr))
    assert abs(y.size - want) <= 8, f"length {y.size} != {want}"

    # A chunked stream must match resampling the whole thing in one go.
    from scipy.signal import resample_poly
    ref = resample_poly(x, 3, 2).astype(np.float32)
    n = min(y.size, ref.size)
    err = float(np.max(np.abs(y[:n] - ref[:n])))
    assert err < 5e-3, f"chunked resample drifts from one-shot: max err {err:.2e}"

    # No clipping, no DC, amplitude preserved.
    assert float(np.max(np.abs(y))) < 1.0, "resampler clipped"
    assert abs(float(np.mean(y))) < 1e-3, "resampler added DC"

    pcm = _pcm16(np.array([-1.5, -1.0, 0.0, 1.0, 1.5], dtype=np.float32))
    got = np.frombuffer(pcm, dtype="<i2")
    assert list(got) == [-32767, -32767, 0, 32767, 32767], list(got)

    # An all-silent warmup must never hit the network.
    m = LiveModel("small", device="cpu", compute_type="int8")
    segs, info = m.transcribe(np.zeros(C.SAMPLE_RATE, dtype=np.float32))
    assert segs == [] and info.language is None, "warmup must short-circuit"
    assert m._local is None, "warmup must not build the local model"

    # The cost fuse must be a real number and well clear of normal dictation.
    assert MAX_STREAM_SECONDS >= 120, "cap below plausible dictation length"
    assert MAX_STREAM_SECONDS <= 3600, "cap high enough to be expensive"

    print(f"ok: resample {sr}->{dst} exact to {err:.1e}, pcm16 clamps, "
          f"warmup short-circuits, no local model built")


def _live(path):
    """End-to-end against a wav file, paced like a real mic."""
    import wave
    with wave.open(path, "rb") as w:
        assert w.getsampwidth() == 2, "want PCM16 wav"
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    assert sr == C.SAMPLE_RATE, f"want {C.SAMPLE_RATE} Hz, got {sr}"

    s = LiveSession()
    block = int(sr * 0.02)                       # 20 ms, like sounddevice
    t0 = time.time()
    for n, i in enumerate(range(0, a.size, block)):
        slack = t0 + n * 0.02 - time.time()
        if slack > 0:
            time.sleep(slack)
        s.feed(a[i:i + block])
    print(f"spoke {a.size / sr:.2f}s in {time.time() - t0:.2f}s wall")
    s.commit()
    t = time.time()
    try:
        text = s.result()
    except Exception as e:                       # noqa: BLE001
        print(f"FAILED: {e}")
        return 1
    print(f"tail (commit -> text): {time.time() - t:.3f}s")
    print(f"transcript: {text!r}")
    return 0


def main():
    if "--check" in sys.argv:
        _check()
        return 0
    if "--live" in sys.argv:
        return _live(sys.argv[sys.argv.index("--live") + 1])
    install()
    return D.main()


if __name__ == "__main__":
    sys.exit(main())
