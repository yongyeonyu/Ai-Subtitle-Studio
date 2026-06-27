DEX_REVIEW_READY

# Reference Fixture Preflight

Scope: Added an accuracy-first preflight before the next STT2/word precision latency candidate can be accepted.

Changed files:

- `tools/verify_reference_fixture_availability.py`
- `tests/test_reference_fixture_availability.py`
- `ACTION_ITEMS.md`
- `AGENTS.md`
- `docs/VALIDATION.md`
- `docs/HANDOFF.md`
- `test_result.md`

Evidence:

- `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.md`
- `output/manual_verification/latest/reference_fixture_availability_20260627/reference_fixture_availability.json`

Validation:

- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m py_compile tools/verify_reference_fixture_availability.py tests/test_reference_fixture_availability.py` -> pass
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest -q tests/test_reference_fixture_availability.py` -> `3 passed`
- `QT_QPA_PLATFORM=offscreen ./venv/bin/python tools/verify_reference_fixture_availability.py --fallback-media "output/_audio_fingerprint/헤이딜러_최종_2c274c4ab434764a8546/헤이딜러_최종_cleaned.wav" --output-dir output/manual_verification/latest/reference_fixture_availability_20260627` -> expected exit `2`

Result:

- The guard works.
- Reference-scored acceptance is currently blocked because the HeyDealer MP4 and matching SRT under `/Volumes/photo/...` are missing.
- Cached HeyDealer WAV exists, but it is fallback-only and cannot approve text/timing/segmentation-affecting latency trims.

Next:

- Restore or mount the real reference media/SRT before adopting any High context-boundary, STT2 collect, word precision collect, worker scheduling, or cleanup latency trim.
