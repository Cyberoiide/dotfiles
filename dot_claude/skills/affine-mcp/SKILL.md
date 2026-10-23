---
name: affine-mcp
description: How to read, search, and edit cbosle's AFFiNE workspaces (self-hosted, https://affine.cyberoiide.qzz.io) via the affine-mcp-server MCP tools (mcp__affine__*). Use whenever the user mentions AFFiNE, wants to find/read/create/update a doc or note, search their knowledge base, manage tags/folders/database blocks/comments in AFFiNE, or references "Sia" or "Fighty" workspace content — even if they don't say "AFFiNE" explicitly (e.g. "check my journal", "what's in the Fighty design system doc", "add a task to my database in affine"). Covers workspace selection between the two configured workspaces (Sia = work, Personal = Fighty project + misc), title-to-ID resolution, and tool sequences for docs/tags/database/comments.
---

# AFFiNE MCP

Two workspaces are configured, reachable via the same MCP connection (`mcp__affine__*` tools, ~95 of them). Every tool takes an optional `workspaceId` — omit it and it falls back to the CLI's saved default (currently Sia), which is often *not* what the user means, so pick explicitly whenever the request has any workspace signal.

| Workspace | ID | Contents |
| --- | --- | --- |
| **Sia** | `7246fcb1-3ebc-43d3-a274-6b1dee5339f6` | Work — ~200 docs, daily journal ("Journal de plus-stage @ Sia"), dated notes, incident/troubleshooting pages |
| **Personal** | `4ef3929b-2332-40ef-8b81-0e7584228a67` | Personal — ~29 docs, the "Fighty" project (Product Design Spec, Index, Design System, Screen Specs, Tech Stack ADR, Data Model) plus misc saved pages |

If the request doesn't clearly point to one (e.g. "search my docs for X"), run `list_docs` or `search_docs` against both rather than guessing, or ask.

## Titles vs IDs — resolve before you act

Nearly every content tool (`get_doc`, `read_doc`, `append_block`, `update_doc_title`, `add_tag_to_doc`, etc.) takes a doc **ID**, not a title. Users always refer to docs by title. Resolve first:

- Know the exact title → `find_doc_by_title` (case-sensitive by default, pass `caseInsensitive: true` if unsure of casing). Returns all matches with `inTrash` flags.
- Fuzzy / partial title, or browsing → `search_docs` (substring match, case-insensitive, ranked by relevance or `updatedAt`).

Both return `inTrash`. Trashed docs still show up in `list_docs`/`search_docs` — check the flag before assuming a match is the live doc, especially when several docs share a title (a common pattern here: an old trashed version plus a current one).

If a search returns more than one live match, surface the options to the user rather than picking one.

## Common workflows

**Find and read a doc**
`search_docs` (or `find_doc_by_title` if the title is exact) → `read_doc` for full content, or `get_doc` for metadata only (title, tags, timestamps, no body).

**Create a new doc**
`create_doc_from_markdown` when you already have Markdown content — much less round-tripping than `create_doc` + `append_block` calls. Use `move_doc` afterward if it needs a specific parent in the sidebar tree, and `list_children` to confirm placement.

In the **Sia** workspace, creating a doc is never done on its own — it always ends with a row in the journal table. See "Adding a note to the Sia journal" below and follow it every time.

Always set an icon after creating: `update_doc_icon` with an emoji that actually represents the doc's content/topic (not a generic 📄/📝). Pick from the content itself — a debug/incident note gets 🐛, a k8s note gets ☸️, an AWS cost note gets 💰, etc. Skip only if the user explicitly says not to.

**Edit an existing doc**
`read_doc` first to see current structure, then:
- `append_markdown` / `append_block` to add content without touching what's there
- `replace_doc_with_markdown` only when the intent is a full overwrite — it replaces the main note wholesale
- `append_semantic_section` to add a titled section to a doc built with `create_semantic_page`'s section skeleton

**Tags**
`list_tags` to see what exists workspace-wide before creating a near-duplicate. `add_tag_to_doc` / `remove_tag_from_doc` take the resolved doc ID. `list_docs_by_tag` for browsing by tag instead of title search.

**Database blocks** (AFFiNE's in-doc tables, e.g. the Fighty project likely has task/schema tables)
`read_database_columns` before any write — you need real column names/types. Then `add_database_row` / `update_database_row` (cells validated per column type: `checkbox` bool, `number`, `date` as `YYYY-MM-DD`, `text`). `read_database_cells` to verify after writing. `compose_database_from_intent` is the fast path for building a new table from a plain-language schema description rather than column-by-column calls.

**Every note — keep only what's important. Always.**
Notes are written to be re-read and replicated later, not to record what happened. Short, skimmable, navigable. This is a standing preference, not a per-note choice: never write the long version and wait to be told to cut it.

Keep:
- **IDs, names, paths, values** needed to redo the thing — put them in a table when there are more than two.
- **The commands that worked** (written human-style, see below), parameterised with `<placeholders>` so they can be re-run in another account/region, not pasted verbatim from one session.
- **Gotchas** — the non-obvious traps, one bullet each, stating the rule rather than retelling the episode.
- **Status / decision** and anything still open, a line each.

Cut:
- Command *outputs*, unless the exact output is the point (an error string worth grepping, a value that can't be derived). Never paste a large JSON blob or a tool dump.
- Dead ends and the investigation's chronology — the conclusion replaces them. A wrong turn only earns a line if it's a reusable trap, and then it belongs in Gotchas as a rule.
- Narration ("then I checked…", "this confirmed that…"), restated headings, and anything inferable from the commands shown.

**Commands — write them the way official documentation does. Always.**
A person will copy these by hand, so each one must look like what you'd find in the tool's own docs (GitLab, AWS, Ubuntu, kubectl…) and give the same result when they run it. The commands you ran yourself through automation (SSM `send-command`, base64-encoded scripts, polling loops) are not what goes in the note. Translate them into the plain interactive command that does the same thing.
- One command per line, in the order a person types them. `sudo` when needed. Prefer the vendor's documented command and flags (e.g. `sudo apt-get install gitlab-ee=<version>-ee.0`, `sudo gitlab-rake gitlab:env:info`) over a hand-rolled equivalent.
- No automation scaffolding: no heredoc-generated scripts, no `base64`, no `while`/`for` polling loops, no `$(date ...)` in names, no `> log 2>&1` / `echo EXIT=$?` wrappers, no `| tr | sed | awk` chains, no `curl -w '%{http_code}'` checks, no `&& echo READY`. If a person would just watch the output or open a page in the browser, say that instead.
- Long-running steps: say "run it inside `tmux`", the way a person keeps a job alive if the session drops. `systemd-run` or `nohup` only when there is really no interactive shell, and then as a short note.
- Verification is what a person reads: "every line starts with `run:`", "returns `(0 rows)`", "open https://… and log in".
- Never document a command you have not checked: it must exist, its flags must be real, and it must work on the target (installed tool, correct path, real output). If you changed it from what you actually ran, verify the new version works the same way (e.g. AWS waiters time out after about 10 min, so show `describe-images … State` to re-check instead).

Structure by **topic**, with `##` headings someone can jump between — not as a numbered replay of the session. If a section doesn't help redo the task or avoid a trap, delete it.

**Writing content — always clean Markdown**
Every content-writing tool (`create_doc_from_markdown`, `append_markdown`, `replace_doc_with_markdown`, the `markdown` field on `append_block`) parses real Markdown into native AFFiNE blocks, so sloppy input becomes visible junk in the doc, not just an ugly string:
- Fence every code block with the correct language (` ```yaml `, ` ```bash `, ` ```python `, ` ```rust `, etc.) — this drives AFFiNE's syntax highlighting, so guess from context (file extension, shell prompts, `kubectl`/`terraform`/import statements) rather than leaving it bare or using ` ```text ` as a default.
- No leftover formatting artifacts: no stray `\n` literals, no doubled blank lines, no dangling list markers or unclosed fences, no HTML leaking in from a copy-paste source. Read back what you're about to send before calling the tool.
- Use real Markdown structure (headings, lists, tables) instead of faking hierarchy with bold text or manual indentation — it round-trips into proper AFFiNE blocks that way.
- `analyze_doc_fidelity` / `export_with_fidelity_report` tell you what will be lossy before you rely on a structure surviving import — check them for anything beyond plain text/headings/lists/code.

**Comments**
`list_comments` → triage → `update_comment`/`create_comment` → `resolve_comment` once addressed.

**Markdown export/backup**
`export_doc_markdown` for a plain backup; `export_with_fidelity_report` when native AFFiNE structures (databases, edgeless canvas) matter and you need to know what will be lossy.

## Adding a note to the Sia journal

**Non-negotiable: every doc created in the Sia workspace gets a row in "Journal de plus-stage @ Sia".** No exceptions, no "the user didn't ask for a row", no separate follow-up step — creating the doc and adding the row are one single task, and the task is unfinished until the row exists. This applies to every `/affine-mcp sia` request and to any doc you create in Sia for any other reason.

**This is the primary way notes get added to Sia** — the doc "Journal de plus-stage @ Sia" (`ZJjbIuuHXjXSb78JbJgBL`, workspace `7246fcb1-3ebc-43d3-a274-6b1dee5339f6`) contains a single big database block that is the *only* place cbosle browses notes. A "new note" always means: create the content doc, then add one row to this table linking to it. Never just create a floating doc and forget the row — an unlinked doc is invisible to how this journal is actually used.

Database block ID: `b3GBxWd-N1`. Columns (from `read_database_columns`):

| Column | Type | id |
| --- | --- | --- |
| Title | title | `title` |
| Category | multi-select | `L93Tpz_HnR` |
| Links | link | `vVcFGWga2E` |
| Créé par | rich-text | `6keSqZPf3b` |
| Date Notion | date | `zgGXTw-cB_` |
| Last Edited | date | `5FD6Uew-vM` |

Steps:

1. **Create the note doc first.** `create_doc_from_markdown` (or `create_doc` + `append_block`/`append_markdown`) in the Sia workspace with the actual note content and a real title (the row's own Title cell is conventionally left blank/single-space — the title lives on the linked doc, matching every existing row). Set a content-relevant icon with `update_doc_icon` (see icon rule above).
2. **Add the row** with `add_database_row`:
   - `docId`: `ZJjbIuuHXjXSb78JbJgBL`
   - `databaseBlockId`: `b3GBxWd-N1`
   - `linkedDocId`: the new doc's ID from step 1 — this is what makes the row open the note when clicked, exactly like every existing row
   - `cells`:
     - `Créé par`: `"Claude"`
     - `Date Notion`: today's date, no need to ask — set automatically every time
     - `Links`: only set when the note itself references an external URL (a PR, dashboard, ticket, doc link); leave unset for self-contained notes
     - `Category`: see tagging rules below
     - `Title`: leave blank/omit, matching the existing convention
3. **Verify with `read_database_cells`** on the new row block ID, and check the returned `linkedDocId` matches the doc from step 1. Do this before telling the user the note is written — a row whose link silently didn't attach looks identical to no row at all in the journal.

### Tagging rules (Category column)

The existing Category options are a mess — some are precise (`k8s`, `AWS`, `debug`, `terraform`), but many are legacy junk from a Notion import: single "options" that are actually several comma-joined tag names stuffed together (e.g. `"SIEM,Stratumn,Terraform"`, `"Error,Fix,MasSeeds"`). Those blobs are past mistakes, not real categories — **never select one for a new note**, and don't bother cleaning up old rows unless explicitly asked.

Going forward, tag every new note the way the existing clean tags already work: **several separate, precise, niche, explicit multi-select values**, not one vague catch-all. Don't reuse an existing option just because it's close enough — think about what actually, specifically describes this note and create new options freely when nothing existing is precise. `add_database_row`/`update_database_row` auto-create multi-select options from the label, so this costs nothing extra.

Good: a note about debugging a CrashLoopBackOff in an EKS pod caused by a missing secret gets `["k8s", "eks", "debug", "secret"]` — not `["Heka"]` or `["debug"]` alone. A note about a GitLab CI pipeline failing on a Terragrunt apply gets `["GitLab", "CI/CD", "Terragrunt", "debug"]`. Think from the content, not from which client/project the note happens to be under — "Heka"/"Sia"/"Stratumn" alone say nothing about *what* the note is about.

## Gotchas

- **Default workspace is sticky but wrong-by-default for cross-workspace asks.** Always pass `workspaceId` explicitly once you know which workspace the user means — don't rely on the fallback.
- **`inTrash` doesn't mean gone.** Trashed docs are still listed and still readable/editable via their ID. Filter them out of search results yourself when the user wants "current" docs.
- **`search_docs` caps at 20 results by default** (raise `limit`, max not fixed but keep it reasonable) and is always case-insensitive; `find_doc_by_title` is the one to reach for when you need an exhaustive exact-title match (case-sensitive by default, up to 200).
- **Edgeless canvas and surface elements** (shapes, connectors, frames on a whiteboard-style doc) are a separate tool family (`get_edgeless_canvas`, `add_surface_element`, `update_frame_children`, etc.) — only relevant if the doc is edgeless-mode, not a normal page. Check `get_doc`/`read_doc` first; don't reach for these unless the content is actually canvas-based.
- **Destructive tools** (`delete_doc`, `delete_workspace`, `delete_folder`, `delete_tag`, `delete_blob`, `delete_comment`, `delete_database_row`, `revoke_access_token`) — confirm with the user before calling, same as any other irreversible action.
- **`get_orphan_docs` is not the way to check journal linkage.** It only counts embed/inline doc references, not database-row links, so every doc reached through the journal table shows up as an orphan — 276 of them in Sia, the journal doc itself included. To confirm a note is properly filed, use `read_database_cells` on its row and check `linkedDocId`, never the orphan list.
