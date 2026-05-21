<!--
Document-Version: 04.00.12-mac-native
Phase: MAC_NATIVE_APPSTORE_V4_0_12_RELEASED
Last-Updated: 2026-05-21
Updated-By: Codex
Purpose: Pointer only. Active execution queue moved to idea_item.md.
-->
# ACTION_ITEMS.md - Queue Pointer

## Current Rule

All active action items, parked action notes, execution order, QA gates, and
rollback rules have been consolidated into `idea_item.md`.

Completed items must be deleted from this file instead of kept as checked
history. This file should remain a pointer unless the owner explicitly asks to
restore a separate action queue.

Use this source of truth:

- `idea_item.md`
- Section: `Active Execution Queue`

## Metadata

```yaml
app_version: "04.00.12"
document_version: "04.00.12-mac-native"
phase: "MAC_NATIVE_APPSTORE_V4_0_12_RELEASED"
active_item_count: 0
queue_source_of_truth: "idea_item.md"
commit_policy: "Commit only when the user explicitly asks."
product_priority: "Accuracy before speed; optimize generation time only with behavior-preserving changes."
```

## Cleanup Note

Completed action-item history and duplicated active queue text were removed from
this file. When the owner says `아이디어 전부 실행해`, execute the consolidated
plan in `idea_item.md` instead of reading a separate action queue here.
