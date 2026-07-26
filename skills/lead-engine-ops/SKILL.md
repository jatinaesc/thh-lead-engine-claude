---
name: lead-engine-ops
description: File and work Bugs & Tasks on the thh-lead-engine Ops Deck via the lead-engine MCP. Use when QA reports a bug/task, or a developer picks up their assigned lead-engine tickets. Enforces the house issue format and token-light reads.
---

# Lead-Engine Ops Deck

Bridge to the lead-engine **Bugs & Tasks** kanban through the `lead-engine` MCP.
Two audiences: **QA files** structured issues fast; **developers read** assigned
issues cheaply. Requires the `lead-engine` MCP server connected.

## Token contract (do not violate)

1. **List before detail.** Start with `list_my_tickets` / `list_tickets` (thin,
   one line per card). Call `get_ticket(id)` for the FULL card only on the one
   picked. Never `get_ticket` a whole list.
2. **Trust the structure.** Cards come back already-structured (Problem / Steps /
   Expected / Actual). Act on the slots directly — do **not** re-summarize or
   re-paraphrase a well-formed card back to the user. That's the double-spend.
3. Tool output is already compact (labels, not int codes, empty fields dropped).
   Pass it through; don't reformat it into something bigger.

## Enums (labels the tools accept)

- **kind**: task · bug · feature_request · idea · incident · tech_debt · spike · improvement
- **status**: todo · in_progress · dev_pushed · dev_qa_passed · prod_pushed · prod_qa_passed · done
- **priority**: low · med · high · urgent   (tasks)
- **severity**: trivial · minor · major · critical   (bugs)
- **effort**: XS · S · M · L · XL

## QA — filing a bug

Gather the slots, then ONE `create_bug` call. House format (auto-assembled by the tool):

```
title:        concise; prefix (Env/Area) when useful — "(Prod) JD generation slow"
problem:      1–2 sentences: what's wrong and where
steps:        ["Log in as recruiter", "Open Jobs", "Click a Paused job", ...]
expected:     what should happen
actual:       what happens instead
severity:     trivial|minor|major|critical   (major = broken flow, critical = data/security/prod-down)
environment:  dev|staging|prod
error_text:   optional — stack trace / technical detail / precise repro conditions
assignee_ids: optional — resolve names with list_users first
attachment_urls: optional — from upload_screenshot(<path>)
```

Rules that match the QA lead's style:
- Always **number** the repro steps. One action per step.
- Always set **severity** and **environment** on a bug.
- Put stack traces / "how it should behave technically" in **error_text**, not the body.
- Screenshots: when the user pastes/points to an image, call `upload_screenshot(<file path>)`
  first, then feed the returned URL into `attachment_urls`. (Pasted images are saved
  to disk by Claude — use that path.)
- If the user is vague, ask ONLY for the missing slot(s) — don't re-ask what they gave.

Filing a **task** instead of a bug → `create_task` (title, description, priority, effort).

## Developer — working assigned issues

1. `list_my_tickets(statuses=["todo","in_progress"])` → pick the card.
2. `get_ticket(<id>)` → read Problem/Steps/Expected/Actual + error_text + attachments.
   Start work directly from those slots.
   - **Screenshots**: the card lists attachment URLs. To actually *see* one, call
     `get_attachment(<url>)` (downloads it local) then open the returned path with
     the **Read** tool. Only fetch attachments when the visual matters — don't
     pull every image reflexively.
3. Moving the card: `move_status(id, "in_progress")` → after deploy `move_status(id, "dev_pushed")`, etc.
4. Need to ask QA something → `comment(id, body, mention_ids=[<qa id>])`.

## QA verify / reject

- Passed on staging → `move_status(id, "dev_qa_passed")`; on prod → `"prod_qa_passed"`; closed → `"done"`.
- **Reject** (send back to the dev) → `add_qa_remark(id, "<what still fails>")`.
  This auto-@mentions assignee + creator and kicks the card back from the
  QA-passed stage to the matching *_pushed stage. Use this, not a plain comment,
  when the fix didn't hold.

## Resolving people

`list_users` → `id  name  (role)`. Cache it for the session; use ids for
assignees, mentions, and creator filters (e.g. `list_tickets(creator_ids=[15])`
for the QA lead's tickets).
