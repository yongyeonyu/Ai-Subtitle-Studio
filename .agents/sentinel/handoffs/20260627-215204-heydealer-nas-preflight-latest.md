# DEX_REVIEW_READY: HeyDealer NAS Preflight Latest

- Scope: owner-required NAS HeyDealer 3-minute generation-latency acceptance gate.
- Command: `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --media "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.MP4" --reference-srt "/Volumes/photo/22_유튜브영상_개인/[20260209]헤이딜러광고/헤이딜러_최종.srt" --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --start-sec 0 --duration-sec 180 --output-dir output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest`
- Result: blocked with expected exit `2`; `reference_media_missing` and `reference_srt_missing`.
- Evidence: `output/manual_verification/latest/heydealer_nas_reference_preflight_20260627_latest/reference_fixture_availability.md`.
- Note: `/Volumes` currently exposes only `Macintosh HD` and `action6`; cached HeyDealer WAV remains fallback-only and was not used for acceptance.
