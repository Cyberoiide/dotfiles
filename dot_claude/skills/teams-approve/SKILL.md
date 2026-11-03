---
name: teams-approve
description: Offer to post "plss approve <MR link>" to the "St🐀umn Core" Teams group chat once you judge a GitLab MR cbosle owns is ready for approval — all review threads resolved, all requested changes done, the discussion with cbosle finished. Always ask cbosle first and post only after an explicit yes. Also use when cbosle says "ask for approval", "ping the team", "send it to stratumn core". Never for Draft MRs, MRs with unresolved threads, or MRs with a failed pipeline.
---

# Ask Stratumn Core to approve an MR

teams-lite runs on claude-host. The two helpers below have the same name and arguments on both machines (chezmoi installs the right version per host):
- on claude-host they talk to teams-lite directly (local websocket + local sqlite),
- on the laptop they forward to claude-host over SSH; `teams-post` falls back to SSM if SSH is down.

So run the commands as written, wherever you are. Never wrap them in `ssh claude-host` yourself.

## When

"Ready" means the work is finished, not just that the MR is open:
- every review thread is resolved (bot threads included),
- every change cbosle asked for is done and pushed,
- nothing is left open in the conversation with cbosle.

Opening an MR or marking it ready is NOT enough on its own.

## 1. Check the MR

```bash
glab mr view <iid> -R git.sia.partners/<group/project> -F json \
  | jq '{web_url, iid, title, draft, pipeline: .head_pipeline.status, blocking_discussions_resolved}'
```

Keep the `git.sia.partners/` host prefix: glab's default host is git.sia-partners.com, which 404s on Stratumn MRs. Stratumn monorepo = `git.sia.partners/stratumn/platform/stratumn`.

Not ready (say why, do not offer to post) if:
- `draft` is `true`
- `blocking_discussions_resolved` is `false`
- `pipeline` is `failed` or `canceled`

A `running`, `manual` or `null` pipeline is fine.

## 2. Check if it was already posted

```bash
~/.local/bin/teams-mr-posted '19:21d2695ae8ff4e25ace9c662e5c326cb@thread.v2' '<web_url>'
```

It searches the whole chat history in teams-lite, from anyone.
- exit 0, prints `<message_id> <date> <sender>`: already posted → this is a **re-ping**.
- exit 1: never posted → this is a **first ask**.
- exit 255 (laptop only): SSH to claude-host is down, so you cannot tell. Say so; do not post.

## 3. Ask cbosle

One line, then stop and wait.

First ask:
> !<iid> looks ready for approval (threads resolved, pipeline <status>). Post "plss approve" to St🐀umn Core?

Re-ping:
> !<iid> was already posted on <date> and is still not approved. Re-ping St🐀umn Core?

Post only on an explicit yes ("oui", "yes", "go", "vas-y"). Anything else: do not post. Ask once per MR per session; if cbosle says no, do not ask again unless the MR changes.

## 4. Post it

First ask:
```bash
~/.local/bin/teams-post '19:21d2695ae8ff4e25ace9c662e5c326cb@thread.v2' \
  "plss approve <web_url>" \
  'plss approve <a href="<web_url>">!<iid> <title></a>'
```

Re-ping:
```bash
~/.local/bin/teams-post '19:21d2695ae8ff4e25ace9c662e5c326cb@thread.v2' \
  "up 🙏 plss approve <web_url>" \
  'up 🙏 plss approve <a href="<web_url>">!<iid> <title></a>'
```

HTML-escape `&`, `<`, `>` in the title before putting it in the third argument.

Success prints `{"message_id":"…","sent":true}`. Tell cbosle in one line: "Posted to St🐀umn Core: !<iid>" (or "Re-pinged …").

## If it fails

| Error | Fix |
|---|---|
| `no running teams-lite backend` | teams-lite is down on claude-host. Tell cbosle; do not retry. |
| `refused: … write token` | backend restarted mid-call. Retry once. |
| SSM `ExpiredToken` / SSO error | `aws sso login --profile code-assist-admin`, then retry. |

Never retry after a timeout without checking the chat: the message may already be posted.
