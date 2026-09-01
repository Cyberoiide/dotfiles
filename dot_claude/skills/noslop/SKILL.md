---
name: noslop
description: Use when reviewing a diff, PR, or MR before merge — before opening a PR, when asked "is this slop", "is this over-engineered", "has this already been done", or when the user invokes /noslop or /noslop ship.
---

# noslop

Pre-merge gate. Kills duplicated work first, complexity second, bugs third.
Wrapper only: review logic lives in the skills it invokes — implement none here.

## Target

- No args: staged + unstaged changes, plus branch commits vs merge-base with main/master.
- PR/MR number or URL as arg: `gh pr diff <ref>` / `glab mr diff <ref>`.
- `ship` as arg: run Ship mode below.

## Pipeline

Gates run in order. A kill verdict ends the review — never review code that should be deleted.

### Gate 1 — already exists?

For each function/feature the diff adds:

1. Search this codebase for an existing helper, util, or pattern that already does it. Search by concept and by name, fast — grep or one Explore agent, not a file-by-file audit.
2. One command for work in flight: `gh pr list --state all --search "<feature>"` (or `glab mr list --search`). Skip silently if the CLI is absent or the repo has no remote.

Hit on the diff's *main purpose* → verdict **ALREADY EXISTS**, stop.
Hit on a piece of it → record as finding `dup: <new thing> re-implements <file:line>`, continue.

### Gate 2 — complexity

Invoke skill `ponytail:ponytail-review` on the target diff. Keep its findings and net-lines score.

### Gate 3 — correctness

Invoke skill `code-review` at medium effort on the same target. Bugs only.

## Report

End with exactly this shape, nothing after it:

1. Verdict line, one of:
   - `ALREADY EXISTS — reuse <what>, delete this diff.`
   - `SIMPLIFY FIRST — N findings below.` (any gate-1 dup or gate-2 finding)
   - `SHIP` (no dups, nothing to cut, no bugs — minor bug-only findings may still say SHIP with the fixes listed)
2. Findings, one line each: `<file>:<line>: <tag>: <what>. <replacement>.`
3. `net: -N lines possible.`
4. One offer: "Apply fixes? Or rerun as `/noslop ship`."

**Report mode never edits.** No file changes, however obvious the fix. Applying anything requires the user's yes or ship mode.

## Ship mode (`/noslop ship`)

Same pipeline, then apply everything autonomously, no prompts:

1. Delete/rewire gate-1 duplications to reuse the existing code.
2. Invoke skill `simplify` to apply the quality fixes.
3. Apply gate-3 bug fixes.
4. Report what changed, same format, verdict reflects post-fix state — but no offer line: ship mode already applied everything it may.

ALREADY EXISTS verdict in ship mode still stops — deleting someone's branch work is a user decision.

## Boundaries

Out of scope: style nits, formatting, praise, refactors beyond the diff.
