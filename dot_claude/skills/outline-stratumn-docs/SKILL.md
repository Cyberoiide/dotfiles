---
name: outline-stratumn-docs
description: Create or update documentation in Outline (wiki.sia.partners) for the Stratumn project. Use whenever cbosle asks to write, add, create, or update a wiki/doc/documentation page for Stratumn — especially anything infra/devops related (Gitlab, Terraform, SSM, CI/CD, architecture). Always places docs inside the Stratumn collection, defaults to the Infra folder (cbosle is devops), follows the existing category tree instead of dumping flat pages, and writes content using the i-have-adhd skill for tone.
---

# Outline docs for Stratumn (infra-first)

cbosle is devops on Stratumn. Default location for any new doc, unless he says otherwise: **Stratumn collection → Infra folder → correct subcategory**.

## Fixed IDs (don't re-look-up every time)

| Thing | ID |
|---|---|
| Stratumn collection | `130d4a3c-157f-459d-b05e-1223f703e702` |
| Infra doc (parent folder) | `f41b0351-fb3c-4d5a-a2de-da980b90ef75` |
| Infra → CI/CD | `59aeafb7-649e-442e-847b-8089b4cef3b8` |
| Infra → Architecture Overview | `033feea4-5b42-4aec-86bf-9dcb1d281b3b` |
| Infra → Stratumn CLI | `49a7a51b-2737-40ca-8bad-f9274cfc5351` |
| Infra → Stratumn CLI → Database | `4aab2f37-70a5-4a8a-866b-0a0cdc9fe6a7` |
| Infra → SSM | `9461179f-ac73-42dc-ab04-bc05ab722686` |
| Infra → Terraform | `40c6f343-fdc3-481c-9fc7-eba392123674` |
| Infra → Gitlab | `97c25c64-1487-47f9-a966-69b6d7545135` |

IDs above can drift (docs get moved/renamed). If a create/move call fails or the tree looks different, re-fetch with `mcp__outline__list_collection_documents` on the Stratumn collection ID and update this table.

You have standing permission to call any `mcp__outline__*` tool without asking first — read, create, update, move. Still confirm before `delete_collection` / `delete_document` (destructive, hard to reverse).

## Placement rule

1. Never dump a new doc flat into the Stratumn collection root. It goes under Infra, or under one of Infra's existing subfolders if the topic matches one (Gitlab config → Gitlab folder, a Terraform module → Terraform folder, a CLI command → Stratumn CLI folder, etc).
2. If the topic doesn't match any existing subfolder, create a new one **nested under Infra** (`parentDocumentId` = Infra doc ID) rather than inventing a new top-level category next to Infra.
3. Before creating, run `list_collection_documents` on the Stratumn collection (or re-check the table above) — skim titles for a doc that's clearly the right parent. Match the existing naming style: short, plain title, no numbering prefix.
4. If genuinely unsure which subfolder fits, ask cbosle rather than guessing — he said the tree is already well-ordered, so don't mess up the order.

## Writing the content

Every document body is written using the **`i-have-adhd`** skill's rules: lead with the action/point, numbered steps for procedures, no preamble/no closing fluff, minimal emoji, short concrete sentences. This is cbosle's own writing style he wants mirrored — plain, direct, skimmable, not corporate wiki-speak.

Before publishing, run the doc against `references/documentation-best-practices.md` — organized/accessible/current/visual-aided/outsider-testable, no jargon/vagueness/rot/hidden placement.

Outline-specific constraint: markdown passed to `create_document`/`update_document` must **not** start with an H1 — the title is a separate field. Start the body with plain text or an H2 (`##`).

Match the tone of existing infra docs in this collection (see `Gitlab`, `Terraform` docs already there): short prose paragraphs, fenced code blocks with the right language tag, tables for anything tabular (security groups, ports, columns), `:::tip` / `:::warning` / `:::success` containers for callouts when relevant. No decorative emoji spam — an icon on the doc itself is fine, emoji inside the body text is not.

## Steps to create a new doc

1. Resolve the parent: pick the right Infra subfolder ID (table above), or the Infra doc ID itself if it's a top-level infra topic.
2. Draft the content following the ADHD + tone rules above.
3. `create_document` with `collectionId: 130d4a3c-157f-459d-b05e-1223f703e702`, `parentDocumentId: <resolved parent>`, `title`, `text` (markdown, no leading H1), `publish: true`.
4. Set an icon matching the topic via the `icon` param on create (or `update_document` after) — same convention as `Gitlab` (💻/`code`) and `Terraform` (🔨) already have icons.
5. Sanity check with `fetch` (resource `document`) on the new doc ID, confirm it landed under the right parent and renders correctly.

## Updating an existing doc

`fetch` (resource `document`) first to read current markdown, then `update_document` with `editMode: "patch"` + `findText` for a surgical change, or `editMode: "append"` for adding a new section. Only use `editMode: "replace"` for a genuine full rewrite — it loses any rich formatting outline can't round-trip through markdown.
