# Speech / STT

This folder points to STT, VAD, LLM, word precision, and latency/default-cache
evidence.

Canonical files:

- `../planning_queue/ACTION_ITEMS.md#g1-stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`
- `../planning_queue/COMPLETED_ACTION_ITEMS.md#stt2--word-precision-generation-latency-profiling-and-accuracy-preserving-trim`
- `../quality_validation/test_result.md`

Rules:

- Do not skip STT2, disable word precision, lower LLM/LoRA/VAD quality policy, shrink STT windows, promote Fast mode defaults, or loosen final subtitle stability gates without owner approval.
- Keep generated/X5 evidence as supporting evidence when NAS HeyDealer first 180 seconds is the active gate.
- Keep collect-cache defaults disabled until explicit owner review promotes them.
