# LeetCode / coding-interview tracker

Personal workspace (`4ef3929b-2332-40ef-8b81-0e7584228a67`), same pattern as the Sia journal / DevOps Interview Notes: a hub doc with one database block, each row linked to its own problem doc.

Hub doc: **"Coding Interview Practice (LeetCode)"** — `bru2bTqxBN`
Database block ID: `hcOPJ405WX`

## Columns

| Column | Type | id |
| --- | --- | --- |
| Title (problem name) | title | `title` |
| Difficulty | select (Easy/Medium/Hard) | `dk3tZL24jz` |
| Topic/Pattern | multi-select | `g80UYaxVFY` |
| Status | select (To Do/Attempted/Solved/Needs Review) | `KfnhTAoqUB` |
| Source | link | `ta-UV6KJ7t` |
| Date Added | date | `MjVB6haRMA` |

`Topic/Pattern` starter options: Array, String, Hash Map, Two Pointers, Sliding Window, Linked List, Stack, Queue, Binary Search, Sorting, Recursion, Backtracking, DP, Greedy, Tree, Graph, Heap, Bit Manipulation. Multi-select auto-creates new options from a label, so add more freely when a problem doesn't fit the starter set — don't force a stretch match.

## Adding a new problem

1. **Create the problem doc first** (`create_doc_from_markdown`, personal workspace). Structure, mostly Python:

   ```markdown
   <LeetCode link if any>

   ## Problem

   <statement / constraints>

   ## My Attempt (first pass)

   ```python
   # what was tried first
   ```

   ## What I Got Wrong

   <one code block per broken intermediate state, in the order it actually happened —
   not a bullet-point list. Each snapshot is the exact code at that point (pull it from
   the live check script's output, don't paraphrase). One short comment directly under
   each block naming the bug in that snapshot: what's broken, why.>

   ## Correct Solution

   ```python
   # working solution
   ```

   Time: O(...) — Space: O(...)
   ```

   **Why code blocks over bullets:** a bullet list describing "overwrote the dict", "wrong return", etc. is a summary — the actual broken code is more readable and more useful to review later than a description of it. Snapshot the real diff-state, comment on it, move to the next snapshot.

2. **Add the row** with `add_database_row`:
   - `docId`: `bru2bTqxBN`
   - `databaseBlockId`: `hcOPJ405WX`
   - `linkedDocId`: the new doc's ID from step 1
   - `cells`: `Difficulty`, `Topic/Pattern` (array of labels), `Status` (start `"Needs Review"` while still working the problem, flip to `"Solved"` once the correct solution lands), `Date Added` (today, `YYYY-MM-DD`), `Source` (LeetCode URL if applicable)
   - Leave the row's own `title` cell blank — title lives on the linked doc, same convention as the Sia journal rows.

3. Optionally verify with `read_database_cells`.

## Live-monitoring a session (hints, no answers)

When cbosle is actively solving in Brave and wants periodic check-ins:

- Read `/tmp/leetcode_check.js` if it exists in the session — a small Node script using `playwright-core` (not the Playwright MCP tool, which is broken on this system: it hardcodes looking for a `chrome` channel binary that doesn't exist here) that connects over CDP (`chromium.connectOverCDP('http://localhost:9333')`) to a separate Brave instance, finds the LeetCode tab, and pulls page title/URL, the Monaco editor's current code (`.view-lines`), and last submission result.
- That separate Brave instance runs on a copied profile dir (cookies/login-data/prefs copied out of the real `~/.config/BraveSoftware/Brave-Browser/Default` into an isolated dir) so it has cbosle's LeetCode login without touching the main browser session or requiring it to be closed.
- Loop cadence: use `/loop` (CronCreate under the hood) at a few minutes, prompt = re-run the check script and report.
- **Hints only, never the fix.** Point at what's wrong and why (wrong loop order, shadowed builtin name, broken indentation, returning the wrong thing) without writing the corrected line for them. Let them arrive at the fix.
- Once they land on a working, accepted solution: update the doc (`replace_doc_with_markdown`, snapshots-in-code-blocks format above) and flip the row's `Status` to `"Solved"`.
