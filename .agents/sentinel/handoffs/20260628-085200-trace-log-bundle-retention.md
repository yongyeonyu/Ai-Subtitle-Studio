DEX_REVIEW_READY
Role: 덱스 closeout
Project: AI Subtitle Studio
Repo: /Users/u_mo_c/Downloads/ai_subtitle_studio
Scope: Trace Log Bundle contract and retention

Summary:
- Added tools/audit_trace_log_bundle.py and tests/test_trace_log_bundle_audit.py.
- Added trace run-directory retention through core/runtime/temp_workspace.py and core/runtime/trace_logger.py.
- The TraceLogger retention policy prunes old runs before creating a new run so the post-start run count stays at most 20.
- The audit proves required temp directories, manifest/latest/events JSONL, exact-frame fps_num/fps_den, bounded media fingerprinting, package collection, and retention.

Artifacts:
- output/manual_verification/latest/trace_log_bundle_retention_audit_20260628/trace_log_bundle_audit.md
- output/manual_verification/latest/trace_log_bundle_retention_audit_20260628/trace_log_bundle_audit.json
- .agents/sentinel/handoffs/20260628-084655-watchdog-handoff-probe.md
- .agents/sentinel/handoffs/20260628-084700-trace-retention-next-gap-scout.md

Validation:
- ./venv/bin/python -m py_compile core/runtime/temp_workspace.py core/runtime/trace_logger.py tools/audit_trace_log_bundle.py tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py -> pass
- QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_trace_logger.py tests/test_trace_log_bundle_audit.py -> 16 passed
- QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_trace_log_bundle.py --output-dir output/manual_verification/latest/trace_log_bundle_retention_audit_20260628 -> pass

Result:
- passed=true
- frame_precision_ok=true
- bounded_media_fingerprint=true
- package_complete=true
- retention_ok=true
- retained_run_count=20/20
- retention_removed_count=5
- trace_disabled=false
- trace_drop_counts={}

Open boundaries:
- Trace files are diagnostic evidence only and must not become subtitle timing, cut-boundary, save-file, or UI state owners.
- Do not add high-frequency per-frame UI trace logging without a separate overhead gate.
- No packaging, signing, DMG, App Store, STT policy, or save-format work belongs to this slice.
