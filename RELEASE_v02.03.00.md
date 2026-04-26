<!--
Document-Version: 02.03.00
Phase: PHASE1-B
Last-Updated: 2026-04-26
Updated-By: Codex with 대표님
Previous-Content: v02.03.00 멀티클립/LLM/NAS/성능 변경 릴리즈 메모
This-Update: 작성자/기존 내용/인계 메모를 포함한 릴리즈 문서 관리 블록 추가
Copilot-Handoff: 이 문서는 커밋 직전 최종 상태 기준으로만 갱신합니다. 중간 작업 중에는 불필요하게 수정하지 않습니다.
-->
# AI Subtitle Studio v02.03.00 Release Notes

**릴리즈 작업일:** 2026-04-26  
**Phase:** PHASE1-B  
**이전 기준:** v02.02.01

---

## 주요 변경

### 멀티클립 안정화
- 기존자막 사전 로드 시 reuse clip index 기록
- backend 단계에서 사전 로드된 SRT를 다시 append하지 않도록 수정
- 기존자막 reuse-only 케이스에서 큐헤더 100% 처리
- 멀티클립 재시작 시 에디터/세그먼트/타임라인/비디오 context clear
- 재시작은 `_sig_restart_multiclip`로 메인 스레드에서 새 run 시작

### LLM Provider 확장
- `core/llm/` 신규 추가
- OpenAI Responses API adapter 추가
- Gemini/OpenAI/로컬 Ollama를 provider 관점으로 분리 시작
- 설정 UI 모델 리스트에 무료/유료 표시 추가
- OpenAI API Key 입력 UI 추가

### API Key 보안
- Google/OpenAI API Key를 `user_settings.json`에 평문 저장하지 않도록 변경
- macOS Keychain / keyring 기반 `secure_keys.py` 추가
- 기존 Gemini API Key는 Keychain으로 이전
- `dataset/custom_defaults.json`, `core/dataset/user_settings.json`에서 평문 key 제거

### 문서/운영 정리
- 작업 버전을 v02.03.00으로 승격
- 전체 `.py` 헤더 `# Version: 02.03.00` 기준으로 통일
- `config.py` APP_VERSION = `02.03.00`
- `AGENTS.md`, `File_structure.txt`, `ACTION_ITEMS.md` 갱신
- `STRUCTURE.txt` 삭제
- 루트 백업 폴더와 create_all 스크립트 정리

---

## 새 액션아이템

- B14: 멀티클립에서 기존자막 사용 질문에 "아니요" 선택 시 기존 SRT 자동 로드 금지
- B14: 확인된 기존 개별 SRT는 기존 백업 규칙에 맞춰 `자막백업/`으로 이동
- R13: 전체 프로젝트 리팩토링 / 리네이밍 / 기능 분할 / 중복 기능 통합 / Phase2 대응

---

## Copilot 인계 메모

- `File_structure.txt`를 구조 문서 기준으로 사용합니다.
- `STRUCTURE.txt`는 삭제되었습니다.
- API Key는 JSON에 저장하지 않습니다.
- OpenAI 호출은 `core/llm/openai_provider.py`를 통해 Responses API를 사용합니다.
- 아직 OpenAI 실호출 테스트는 API Key 발급 전이라 미완료입니다.
- B14, 오디오 프리셋, NAS 자동시작은 이번 작업에서 구현되었습니다.

## 2026-04-26 추가 구현

- B14: 기존자막 사용 질문에 "아니요" 선택 시 기존 개별 SRT를 `자막백업/`으로 이동
- 오디오 프리셋 추가: `dataset/audio_presets.json`, `core/audio/audio_presets.py`
- 상세 설정 UI에 오디오 프리셋 콤보박스 추가
- NAS 자동시작 watcher 추가
- iCloud/NAS 동시 ON 시 iCloud 우선, NAS watcher는 중지


## 2026-04-26 NAS 자동화 UI 보강

- 메인 NAS 자동 처리 카드에 전체 하위 폴더 표시 및 스크롤 추가
- 폴더 및 파일 선택창에 `취소` 버튼 추가
- 폴더 행에 `[  ] 제외` 표시를 추가하고 자동감지 제외 폴더 저장
- NAS 자동 처리 카드에 `대기 :` / `작업완료` 요약 표시 추가
- NAS 감시는 1분 주기, 최하위 폴더 용량이 5분간 변하지 않으면 자동 시작
- 프로젝트 하위 카메라 폴더 단위로 이름순 처리, 완료 시 폴더 단위 장부 완료 처리
- 작업 완료 시 로그에 폴더명/파일 수/용량/소요시간 요약 출력
- `경로설정`을 `자동설정`으로 변경
- 메인 하단에 `자동시작 ON/OFF` 토글 추가, `user_settings.json` 저장
- 자동설정에 빠른모드/품질모드/프리셋 모드 선택과 AI 설정/상세설정 바로가기 추가

## 2026-04-26 LLM/성능 보강

- LLM 모델 목록에 전체/무료/유료 필터 추가
- Ollama 추천 모델 목록 및 설정창 설치/삭제/새로고침 추가
- 오디오 프리셋 기본값을 전체 상세 파라미터 포함 형태로 갱신
- requirements.txt 삭제, requirements-mac.txt / requirements-windows.txt 2개 운영으로 정리
- STT 선추출 범위를 기본 3개 파일까지 확장
- VAD none 강제 분할을 병렬 ffmpeg 청크 생성으로 변경
- 비디오 플레이어 UI 타이머 기본 33ms로 완화해 재생 끊김을 줄임
