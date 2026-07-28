#!/usr/bin/env bash
# PostToolUse(Bash): when a GitLab MR URL shows up in a command or its output and the
# current branch names a Linear ticket, tell Claude to attach the MR to that ticket.
# ponytail: no Linear API call here, no token to manage — the hook just injects context
# and lets Claude use the already-connected Linear MCP tools.
set -uo pipefail

# ponytail: STMN is the only Linear team in use; add prefixes here if that changes.
TICKET_RE='[Ss][Tt][Mm][Nn]-[0-9]+'
MR_RE='https://git\.sia\.partners/[A-Za-z0-9._/-]+/-/merge_requests/[0-9]+'

payload=$(cat)

url=$(printf '%s' "$payload" \
  | jq -r '[(.tool_input.command // ""), (.tool_response | tostring)] | join("\n")' 2>/dev/null \
  | grep -oE "$MR_RE" | head -n1)
[ -n "$url" ] || exit 0

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
ticket=$(printf '%s\n%s' "$branch" "$payload" | grep -oE "$TICKET_RE" | head -n1 | tr '[:lower:]' '[:upper:]')
[ -n "$ticket" ] || exit 0

jq -n --arg t "$ticket" --arg u "$url" '{
  hookSpecificOutput: {
    hookEventName: "PostToolUse",
    additionalContext: ("GitLab MR \($u) belongs to Linear ticket \($t). Link it now: call mcp__plugin_linear_linear__get_issue on \($t) to check its attachments, and if this MR URL is not already there, call mcp__plugin_linear_linear__create_attachment with issueId \"\($t)\", url \"\($u)\", and a title like \"MR !<number>\". If it is already attached, do nothing and do not mention it.")
  }
}'
