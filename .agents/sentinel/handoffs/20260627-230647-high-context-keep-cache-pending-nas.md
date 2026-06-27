DEX_REVIEW_READY

# High Context Keep Cache Pending NAS

- Implemented strict High context-boundary keep/no-correction cache and benchmark `--setting` overrides.
- Local guards passed: py_compile, `tests/test_subtitle_context_refiner.py` (`8 passed`), verifier stage-summary subset (`2 passed, 13 deselected`), and benchmark setting parser subset (`1 passed, 32 deselected`).
- Owner-required NAS HeyDealer first 180s acceptance is blocked: `/Volumes/photo` is not mounted as the SMB share, exact MP4/SRT are unavailable, SMB remount attempts did not produce a usable volume, `ping 192.168.0.5` had `100.0% packet loss`, and direct `mount_smbfs` timed out.
- Next Dex action: mount/restore the NAS HeyDealer MP4/SRT, run the same benchmark twice with `subtitle_llm_context_keep_cache_path=output/manual_verification/latest/high_context_keep_cache_20260627/keep_cache.json`, then accept the second cache-hit run with `tools/evaluate_reference_benchmark_acceptance.py`.

Update: owner later said NAS was off and asked Dex to generate/verify a video. The synthetic pass is recorded in `.agents/sentinel/handoffs/20260627-231900-high-context-keep-cache-synthetic-pass.md`.
