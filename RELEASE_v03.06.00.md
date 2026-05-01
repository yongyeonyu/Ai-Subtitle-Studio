<!--
Document-Version: 03.06.00
Phase: PHASE2
Last-Updated: 2026-05-02
Updated-By: Codex with 대표님
Previous-Release: v03.05.00
-->
# RELEASE v03.06.00

## 핵심 요약
- v03.05.01부터 v03.05.10까지의 오디오/STT/타이밍 안정화 묶음을 v03.06.00 릴리즈로 고정했습니다.
- 음성 향상 후보는 RNNoise, Resemble Enhance, ClearVoice를 앱 설정과 실행 경로에 연결했고, 실패 시 기존 FFmpeg 정제로 안전하게 이어집니다.
- VAD 후보는 TEN VAD와 Silero fallback을 함께 사용하도록 정리했습니다.
- STT1/STT2 앙상블은 단어 단위 ROVER 계열 병합과 저신뢰 교체 정책으로 강화했습니다.
- 자막 시간은 Whisper 단어 timestamp와 VAD 음성 섬을 우선해 확정하고, `간격` 설정은 보조 조건으로 사용하도록 바꿨습니다.

## 오디오 / VAD
- RNNoise 실행 파일 경로 탐색과 `RNNOISE_BINARY` 환경변수 경로를 지원합니다.
- Resemble Enhance는 격리 설치 환경과 `RESEMBLE_ENHANCE_BINARY`를 우선 탐색하며, mps/cuda/cpu 장치를 명시해서 실행합니다.
- Resemble Enhance runner에서 `torchaudio.load/save`의 `Path` 인자 호환 문제를 보정했습니다.
- ClearVoice와 TEN VAD는 앱 실행 Python/runtime에서 import 가능한 경로를 맞추고, 실패 시 기존 흐름으로 fallback합니다.
- FFmpeg/RNNoise/ClearVoice 실행 명령의 `env` 중복 전달 오류를 수정했습니다.

## STT / 토큰
- Hugging Face Token을 AI 설정 화면에서 저장할 수 있게 했고, 보안 저장소를 통해 `HF_TOKEN`/`HUGGING_FACE_HUB_TOKEN` 환경변수에 주입합니다.
- Transformers Whisper worker는 deprecated `torch_dtype` 경고를 피하고, 저장된 HF Token을 모델 다운로드 요청에 사용합니다.
- STT1 절대 우선 정책을 완화하고, 단어별 시간 겹침/텍스트 유사도/신뢰도 기반으로 STT2 후보가 교체될 수 있게 했습니다.
- 숫자, 짧은 고유표현, 보호 단어는 과도하게 교체되지 않도록 guard를 유지합니다.

## 자막 시간 / 후처리
- LLM 자막 분할 결과가 원본 Whisper word timestamp를 보존하도록 했습니다.
- `core/engine/word_resegmenter.py`는 큰 `간격` 설정이 있어도 실제 단어 gap과 VAD 섬 경계를 우선해 자막을 나눕니다.
- `core/subtitle_quality/timestamp_regrouper.py`는 최종 자막 시작/끝을 단어 edge와 가까운 VAD boundary에 snap합니다.
- 단일클립/멀티클립 파이프라인 모두 `vad_segments`를 자막 최적화 단계에 전달합니다.

## UI / 실행 안정성
- 사이드바 큐 리스트는 순서 중심 표시로 정리하고, 완료는 초록색, 미완료는 노란색 계열로 표시합니다.
- 예상 시간 텍스트 위치를 조정해 큐 행에서 더 읽기 쉽게 했습니다.
- 재시작 시 에디터 텍스트, 타임라인 캔버스, 글로벌 캔버스, gap/VAD/edit/drag 상태를 초기화하도록 보강했습니다.
- 홈 이동 시 진행 중인 백엔드/STT worker를 중단하고, 늦게 도착한 러프컷 draft callback이 화면에 붙지 않도록 막았습니다.
- 홈 이동 시 Ollama 로컬 LLM 모델 언로드 요청을 보냅니다.

## 의존성 / 설치
- Demucs는 requirements와 모델 후보에서 제외했습니다.
- RNNoise, Resemble Enhance, ClearVoice, TEN VAD 관련 선택 후보를 macOS/Windows requirements와 모델 레지스트리에 반영했습니다.
- Resemble Enhance 대용량 모델 파일은 Git LFS 기반 외부 캐시/격리 환경에서 사용하며 저장소에는 포함하지 않습니다.

## 제거 / 영향 범위
- Demucs 관련 노출은 v03.05.00에서 제거된 상태를 유지합니다.
- 이번 릴리즈에서 공개 `def`, `class`, UI action, signal, slot을 삭제한 변경은 없습니다.
- `.codex_work/`, `checkpoints/`, `dataset/video_preview_cache/`는 로컬/캐시 산출물이며 릴리즈 커밋 대상이 아닙니다.

## 검증
- `QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests`
  - exit code 0
- module-by-module unittest sweep
  - `MODULE_SWEEP_OK`
- Python AST 검사
  - `AST OK: 224 files`
- offscreen UI smoke
  - `UI smoke OK`
- `git diff --check -- . ':(exclude)dataset/video_preview_cache'`
  - exit code 0
- `python3.11 -m pip check`
  - `No broken requirements found.`
- 루트 금지 파일 검사
  - 금지 파일 없음
