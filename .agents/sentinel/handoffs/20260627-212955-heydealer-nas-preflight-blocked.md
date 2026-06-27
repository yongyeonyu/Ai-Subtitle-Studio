DEX_REVIEW_READY

# NAS HeyDealer 3-Minute Preflight Blocked

## Scope

- Owner required the next generation-latency test to use the NAS HeyDealer 3-minute video.
- Dex ran the reference fixture preflight against the NAS MP4/SRT paths and did not run X5 or fallback audio as an acceptance substitute.

## Evidence

- Report: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.md`
- JSON: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627/reference_fixture_availability.json`
- Result: expected exit `2`, `ready_for_reference_scored_benchmark=false`
- Blocking reasons: `reference_media_missing`, `reference_srt_missing`
- Fallback cached HeyDealer WAV exists, but remains instrumentation/structural-stability only and cannot approve latency trims.

## Review

- Accept as a blocked fixture gate, not as a failed app behavior test.
- Next action is to mount/restore `/Volumes/photo/.../헤이딜러_최종.MP4` plus matching `.srt`, then rerun the 3-minute benchmark before evaluating any new latency candidate.
