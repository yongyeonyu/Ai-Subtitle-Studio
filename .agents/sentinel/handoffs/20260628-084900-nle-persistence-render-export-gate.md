DEX_REVIEW_READY
role: 덱스
project: AI Subtitle Studio
repo: /Users/u_mo_c/Downloads/ai_subtitle_studio
scope: NLE persistence render/export gate

summary:
- Strengthened the source-app NLE persistence cutover audit with a render/export parity fixture.
- The audit now writes and reopens a legacy project with roughcut/export outputs, then requires stable NLE projection across source_subtitles, final_overlay, global_canvas, roughcut_sidecar, and exported_assets before reporting prep_ready.
- Persisted NLE disk-format cutover remains blocked. No UI/UX, subtitle generation, STT/STT2, word precision, save-file format, packaging, App Store, or runtime editor behavior changed.

evidence:
- audit: output/manual_verification/latest/nle_persistence_render_export_gate_20260628/nle_persistence_cutover_audit.md
- json: output/manual_verification/latest/nle_persistence_render_export_gate_20260628/nle_persistence_cutover_audit.json
- jammini scout: .agents/sentinel/handoffs/20260628-083300-nle-persistence-next-gap-scout.md
- route probe: .agents/sentinel/handoffs/20260628-082348-watchdog-handoff-probe.md

verification:
- ./venv/bin/python -m py_compile tools/audit_nle_persistence_cutover.py tests/test_nle_persistence_cutover_audit.py -> pass
- QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_nle_persistence_cutover_audit.py tests/test_project_nle_render_export_parity.py -> 7 passed
- QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/audit_nle_persistence_cutover.py --output-dir output/manual_verification/latest/nle_persistence_render_export_gate_20260628 -> pass

result:
- prep_ready true, persistence_cutover_ready false.
- operation roundtrip family count 10, all passed.
- render/export parity stable true, storage clean true.
- stable surfaces: source_subtitles, final_overlay, global_canvas, roughcut_sidecar, exported_assets.
- final invalid/non-monotonic/overlap 0/0/0 and global max active 1.

next:
- Do not persist nle, nle_snapshot, or _nle_project_state to .aissproj until a separate compatibility gate is explicitly approved.
