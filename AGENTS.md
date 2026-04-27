<!--
Document-Version: 02.06.00
Phase: PHASE1-C
Last-Updated: 2026-04-28
Updated-By: Codex with 대표님
Previous-Content: v02.04.00 PHASE1-C 기능 보존형 Apple 스타일 UI 개선 완료 상태
This-Update: v02.06.00 P6 멀티클립 STT/LLM 병렬 파이프라인 구현 및 핸드오프 갱신
Copilot-Handoff: v02.06.00 커밋 기준. P6는 core/pipeline/multiclip_pipeline.py에서 STT worker와 LLM worker를 분리해 구현했습니다. 전역 메뉴바는 ui/menu_bar.py, 공용 아이콘/스타일은 ui/style.py, 통합 대시보드는 ui/main/main_window.py와 ui/home_ui.py를 먼저 확인하세요. 다음 작업은 v02.07.00부터 진행합니다.
-->
# AGENTS.md — AI Subtitle Studio 개발 가이드

## 프로젝트 개요
- **프로젝트명**: AI Subtitle Studio
- **개발자**: 대표님
- **AI 어시스턴트**: Microsoft Copilot
- **목적**: macOS / Windows에서 동작하는 AI 기반 자막 생성·편집·자동화 앱 개발

---

## 🎯 최종 목표

### 1) macOS / Windows 데스크탑 앱
#### Phase1
- Whisper 기반 STT
- 자막 편집
- 화자 분리
- 멀티클립 처리
- 자막 저장 / 출력

#### Phase2
- Gemma4 등 AI 기반 **자동 러프컷 편집**
- 자막 생성 → 러프컷 → 출력까지 원스톱 자동화

#### Phase3
- 프록시 업로드
- 외부 서비스 연동
- API / 자동화 고도화

### 2) iPad 앱 (유료 출시 예정)
- 자막 에디터 중심 모바일 앱
- 무료: 자막 편집 / 타이밍 조정
- 유료: Whisper STT + LLM 자막 최적화 + 자동 화자 분리

---

## 🖥️ 개발 환경

### 회사 (Windows)
- Windows 11 + CUDA GPU
- Python 3.11
- faster-whisper (CUDA)
- 주 작업:
  - Windows 기능 통합
  - 모델 관리
  - 배치 처리
  - faster-whisper subprocess worker

### 집 (macOS)
- MacBook Air (Apple Silicon)
- Python 3.11 (Homebrew / venv)
- MLX Whisper
- 주 작업:
  - UI/UX
  - 리팩토링
  - 버그 수정
  - MLX persistent worker

### 공통
- PyQt6
- ffmpeg
- Ollama / Gemini API / OpenAI API
- Git (main 브랜치 단일 운영)

---

## 🔧 코드 수정 원칙

### 최우선 원칙
**모든 코드 수정은 create_all 계열 Python 스크립트로 수행합니다.**

즉,
- 수동 편집보다 `create_all_X.py` 우선
- 스크립트가 파일 읽기 → 패치 → 백업 → 검증 → 저장까지 수행
- 사람이 직접 파일을 열어 편집하는 방식은 원칙적으로 지양

---

## create_all 패턴 운영 규칙

### 기본 원칙
1. **수정 전 백업 생성**
2. **패치 후 AST 문법 검사**
3. **결과를 `[OK] / [SKIP] / [WARN]` 형태로 출력**
4. **동일 스크립트 재실행 시 재현 가능해야 함**
5. **가능하면 여러 파일 수정도 한 번에 묶어서 처리**

### 명명 규칙
- `create_all.py`
- `create_all_b.py`
- `create_all_c.py`
- ...
- `create_all_x.py`

### 출력 규칙
- `[OK]` 수정 완료
- `[SKIP]` 변경 없음
- `[WARN]` 대상 없음 / 패턴 불일치

### 백업 규칙
- `_backup_x_YYYYMMDD_HHMMSS/` 형식 사용

---

## ✅ 스크립트 작성 규칙 (중요)

### 1) Base64 사용 금지
- Base64는 사용하지 않음
- 이유:
  - 파일 크기 증가
  - 디버깅 어려움
  - 사람이 즉시 검토 불가

### 2) 긴 스크립트는 `repr()` 임베딩 우선
- 긴 텍스트/파일 전체 교체 시
- **repr() 임베딩 방식 우선**
- 문자열 escape 실수 줄이고 안정성 확보

### 3) 링크 출력 전 자동 refresh
- 파일 생성 후 바로 링크 출력하지 않음
- 반드시:
  1. 파일 생성
  2. `ast.parse()` 재검사
  3. 같은 경로에 다시 write (refresh)
  4. 그 후 링크 출력

### 4) 링크 불안 시 처리
- 즉시 재발급
- 필요 시 파일명 변경 후 새 링크 생성

---

## ⚠️ 한글 / 인코딩 주의

### 원칙
- 한글 문자열 직접 매칭은 최대한 피함
- 가능하면 **구조 기반 / 코드 패턴 기반 매칭**
- 긴 한국어 UI 문자열은 파일 전체 교체 또는 repr 임베딩 우선

### 인코딩
- UTF-8 고정
- PowerShell / macOS zsh 차이 고려
- `.write_text(..., encoding="utf-8")` 기본 사용

---

## 🧭 운영 방식

### Windows에서는
- PowerShell 명령 사용
- faster-whisper 중심
- CUDA 경로 / 모델 캐시 / subprocess worker 확인

### macOS에서는
- zsh / bash 명령 사용
- PowerShell 명령 사용 금지
- MLX Whisper / UI 중심 작업

### 환경 차이 주의
- Windows 명령:
  - `Get-Content`
  - `Select-String`
- macOS 명령:
  - `python3 - << 'PY'`
  - `grep`
  - `sed`
  - `find`

---

## 📁 폴더 구조 (기준: v02.06.00)

```text
ai_subtitle_studio/
├── main.py
├── config.py
├── logger.py
├── core/
│   ├── pipeline/
│   ├── audio/
│   ├── engine/
│   ├── project/
│   └── ...
├── ui/
│   ├── main/
│   ├── editor/
│   ├── menu_bar.py
│   ├── style.py
│   ├── settings/
│   ├── timeline/
│   ├── project/
│   └── dialogs/
├── dataset/
├── output/
└── voice_data/
```

---

## 📐 코드 원칙

1. **헤더 통일**
   - 모든 `.py` 파일 첫 줄:
     - `# Version: 02.06.00`
     - `# Phase: PHASE1-C`

2. **파일 분할**
   - 기능별로 분리
   - 과도한 단일 파일 지양

3. **폴더 이동**
   - 필요 시 shim → 안정화 확인 → shim 제거

4. **Phase2 확장 고려**
   - 폴더 구조 / 클래스 분리는 Phase2 자동 러프컷 확장 고려

5. **Whisper 모델 존중**
   - 사용자가 `large-v3` 선택 시 자동 다운그레이드 금지

6. **UI 수정 시**
   - 대표님이 의도한 레이아웃 유지 우선
   - 기능보다 시각적 일관성 / 사용감 우선 확인

---

## 📌 버전 규칙

### 앱 버전
- `config.py` → `APP_VERSION`

### 파일 버전
- 각 `.py` 헤더 버전 사용

### 증가 규칙
- 기능 추가 → 마이너/중간 버전
- 안정화/버그 수정 → 패치 버전
- PHASE1-B 시작 버전은 `02.00.00`

---

## 🗂️ 작업 방식

### 기본 순서
1. 현상 확인
2. 관련 코드 확인
3. 이미 수정된 것 / 안 된 것 분리
4. 남은 것만 create_all로 묶기
5. 실행 로그 확인
6. 통과 후 커밋

### 응답 방식
- 한 번에 너무 크게 가지 않음
- **한 스텝씩**
- 각 스텝마다 필요한 코드 / 로그만 요청
- 불필요한 설명 최소화

---

## 🚨 예외 규칙: 수동 수정 허용 범위

원칙은 create_all이지만, 아래 경우는 **응급조치로 수동 수정 허용**:

1. create_all 자체가 깨져서 반복 실패할 때
2. 매우 짧은 1줄/2줄 수정으로 즉시 복구 가능한 경우
3. 현 시점에서 작업을 멈추면 전체 흐름이 끊기는 경우

단,
- 수동 수정 후 반드시 다음 단계에서 create_all 또는 정리본 반영
- 수동 수정은 **임시 복구**로 취급

---

## 🔊 화자 학습 규칙

### 저장 경로
- `voice_data/` 사용
- 기존 `dataset/my_voice.wav`는 legacy 취급

### 파일 규칙
- 예:
  - `voice_data/spk1_voice.wav`
  - `voice_data/spk2_voice.wav`
  - `voice_data/spk3_voice.wav`

### 기존 파일 마이그레이션
- `dataset/my_voice.wav`
  → `voice_data/voice_backup/my_voice_00.wav` 백업
  → `voice_data/spk1_voice.wav`로 이동

### 세그먼트 우클릭 학습
- 자막 세그먼트 우클릭 메뉴에서
  - `음성 화자로 학습 → 화자 1/2/3`
- 파일명 입력창 표시
- ffmpeg로 WAV 추출
- 저장 후 로그 출력

### 학습 데이터 사용 로그
- diarize에서 학습 데이터 사용 시 로그 출력
- 캐시 사용 시 로그가 생략될 수 있으므로 speaker cache 주의

---

## 🧪 디버깅 원칙

### false success 금지
- 실패했는데 성공 로그 출력되는 구조 금지
- 세그먼트 0개면:
  - 저장 금지
  - 완료 로그 금지
  - 오류 로그로 종료

### worker 출력
- stdout / stderr 구분 철저
- `\n` 리터럴 실수 금지
- JSON line protocol 깨지지 않도록 주의

### 캐시 주의
- `*_speaker_cache.json`
- 캐시가 남아 있으면 학습 데이터 로그/재계산 안 보일 수 있음

---

## 🏠 집 / 🏢 회사 Git 운영 규칙

### 회사
- 커밋 후 가능하면 바로 push
- Windows 전용 수정 반영

### 집
- 작업 전 `git pull`
- 회사 커밋 유무 먼저 확인
- 원격에 없으면 집에서는 필요한 부분만 재구성

### 중요
- 회사 작업 후 push 누락 주의
- 맥에서 `git log --all --oneline | grep <hash>`로 확인 가능

---

## ✅ 현재 유지하고 싶은 작업 스타일

1. 한 스텝씩 진행
2. 먼저 코드/로그 확인
3. 이미 수정된 것 제외
4. 남은 것만 create_all
5. 긴 스크립트는 repr() 임베딩
6. 링크 출력 전 refresh
7. 필요하면 짧은 응급 수동 수정 후 정리
8. 대표님이 원하는 UI/동작 우선 반영

---

## 📌 현재 확정된 UI/운영 메모

### 화자 설정 UI
현재 방향:
```text
[목소리학습] SPK1_VOICE.WAV [재생버튼]
[목소리학습] 학습 데이터 없음 [ ]사용
[목소리학습] 학습 데이터 없음 [ ]사용
```

- 재생 버튼은 재생/정지 가능
- 정렬은 최대한 동일한 x축 유지
- 간격은 과도하게 넓히지 않음

---

## 🔮 남은 작업 운영 방식

### PHASE1-B
- 버그 수정
- Windows/맥 정합성 확보
- create_all 기반 안정화
- UI/UX 마감

### PHASE2 이상
- 자동 러프컷
- 알림 / 도움말 / 프리셋
- iPad 연동
- API / 자동화

---


### NAS 자동처리 규칙 (v02.03.00)
- 메인 화면 `NAS 자동 처리`는 NAS 루트의 모든 하위 폴더를 보여주며, UI가 넘치면 스크롤로 처리합니다.
- 자동감지 제외 폴더는 폴더 선택창의 `[  ] 제외` 체크로 지정하고 `dataset/folder_settings.json`의 `nas_excluded_folders`에 저장합니다.
- NAS 감시는 1분마다 실행합니다.
- 자동 시작 조건은 최하위 작업 폴더 용량이 5분간 변하지 않는 것입니다.
- 프로젝트 폴더 아래 카메라 폴더가 있으면 카메라 폴더 이름순으로 하나씩 큐에 전달합니다.
- 폴더 작업이 완료되면 `auto_tracker.json`에 폴더와 파일 완료 상태를 남기고 로그에 파일 수/용량/소요시간 요약을 출력합니다.
- iCloud와 NAS 자동감지가 동시에 켜져 있으면 iCloud가 우선입니다.
- 메인 하단 `자동시작 ON/OFF`는 `dataset/user_settings.json`의 `auto_start_enabled`에 저장합니다.
- `자동설정`의 자동 처리 모드는 `auto_start_mode` 값으로 저장하며 `fast`, `quality`, `preset`을 사용합니다.

## 📚 문서 최종 갱신 규칙

### 대상 문서
- `AGENTS.md`
- `ACTION_ITEMS.md`
- `File_structure.txt`
- `RELEASE_v02.04.00.md`
- `RELEASE_v02.06.00.md`

### 운영 원칙
1. 위 문서들은 **커밋 직전 최종 업데이트**로 반영합니다.
2. 중간 작업 중에는 불필요하게 갱신하지 않습니다.
3. 문서 갱신 시 상단 주석에 다음 내용을 유지합니다.
   - `Document-Version`
   - `Phase`
   - `Last-Updated`
   - `Updated-By`
   - `Previous-Content`
   - `This-Update`
   - `Copilot-Handoff`
4. 기존 내용이 무엇이었는지 요약을 남겨 Copilot이 변경 맥락을 이어받을 수 있게 합니다.
5. 대표님과 Codex/Copilot이 한 작업 내용 중 다음 세션에 필요한 내용은 `AGENTS.md`, `ACTION_ITEMS.md`, `File_structure.txt`, 릴리즈 노트에 반영합니다.
6. 완료되어 더 이상 추적할 필요가 없는 중복/낡은 내용은 삭제하거나 완료 섹션으로 이동합니다.
7. v02.06.00 작업 중 생성되는 문서도 v02.06.00 기준으로 관리합니다.

## 마지막 원칙
- Copilot은 **대표님의 코딩 파트너**로 동작
- 설명보다 **실제 수정과 검증** 우선
- 항상 현재 작업 맥락을 유지
- 응답은 존댓말
- 가능하면 짧고 정확하게


---

## 🧠 v02.06.00 현재 작업 맥락

- 현재 릴리즈 버전: **v02.06.00**
- 다음 수정 시작 버전: **v02.07.00**
- PHASE1-C Apple 스타일 UI 개선은 기능 보존 원칙으로 반영되었습니다.
- P6 안정화/성능 패치:
  - `core/pipeline/multiclip_pipeline.py`에서 멀티클립 STT worker와 LLM worker를 분리했습니다.
  - 클립1 Whisper 완료 후 클립2 Whisper가 바로 시작되고, 동시에 LLM은 클립1을 최적화합니다.
  - append 순서는 LLM worker 단일 순서 큐로 클립1 → 클립2 → 클립3을 유지합니다.
  - 실제 멀티클립 장시간 파일에서는 `ACTION_ITEMS.md`의 `CHECKPOINT-P6-PARALLEL`을 확인하세요.
- 전역 메뉴:
  - `ui/menu_bar.py`가 하단 실행 메뉴와 상단 상태 레일을 관리합니다.
  - 불필요해진 전역 `이전` / `다음` 액션은 제거했습니다.
  - 창 폭이 화면 절반 이하가 되면 메뉴 버튼 텍스트는 숨고 아이콘만 남습니다.
- 통합 화면:
  - `ui/main/main_window.py`와 `ui/home_ui.py`가 대시보드 중심 화면을 구성합니다.
  - 왼쪽 사이드바에는 홈/자막 편집/프로젝트/Phase2/Phase3/최근 작업, iCloud/NAS 상태, 프로젝트/영상/자막 정보가 있습니다.
- 에디터/비디오:
  - 비디오 subtitle overlay와 자막 에디터 자동 스크롤은 재생 중 가볍게 동기화합니다.
  - 디테일 타임라인은 다이아몬드/화살표/무음 세그먼트 affordance를 유지합니다.
- 설정 UI:
  - `ui/style.py`의 `line_icon()`, `button_style()`, `settings_dialog_stylesheet()`를 우선 사용합니다.
  - 설정 하단 버튼은 `ui/settings/settings_common.py` 공통 헬퍼를 통해 아이콘과 크기를 맞춥니다.
- `STRUCTURE.txt`는 삭제 예정/삭제 완료 문서이며, 구조 문서는 **File_structure.txt**를 기준으로 봅니다.
- LLM은 3-provider 방향:
  - Ollama: 무료/로컬, 기본 우선
  - Gemini: API, 무료 제한/유료 병행
  - OpenAI: API, 저비용/고품질 선택
- API Key는 평문 JSON 저장 금지:
  - macOS: Keychain
  - Windows: Credential Manager 또는 keyring
  - `user_settings.json`에는 provider/model/저장 여부만 기록
- macOS 성능 방향:
  - MLX Whisper persistent worker 유지
  - 모델 preload / 오디오 prefetch / UI update throttling 우선
  - 배터리 절약보다 STT 속도 우선

## 📌 v02.06.00 즉시 주의할 항목

1. 멀티클립에서 기존자막 사용 질문에 **아니요** 선택 시:
   - 기존 SRT 자동 로드 금지
   - 확인된 개별 SRT는 `자막백업/`으로 이동
   - 에디터는 빈 상태로 시작
2. 프로젝트 루트에 `_backup*/`, `create_all*.py`를 장기 보관하지 않습니다.
3. 대규모 리팩토링은 `ACTION_ITEMS.md`의 R13 기준으로 영역별 진행합니다.
4. PHASE1-C 완료 항목은 `ACTION_ITEMS.md`에서 삭제했고, 실사용 확인이 필요한 항목만 CHECKPOINT로 남겼습니다.
5. 다음 채팅에서는 `ACTION_ITEMS.md`의 CHECKPOINT와 Phase2/Phase3 항목을 기준으로 이어가면 됩니다.

### LLM / Ollama / 성능 규칙 (v02.06.00)
- LLM 모델 UI는 `전체/무료/유료` 필터를 제공합니다. 무료는 Ollama 로컬 및 무료/제한 API, 유료는 과금 API 모델입니다.
- Ollama 추천 모델은 `core/model_manager.py`의 `OLLAMA_RECOMMENDED_MODELS`를 기준으로 표시하고, 설정창에서 `ollama pull` / `ollama rm`으로 설치/삭제합니다.
- requirements는 `requirements-mac.txt`, `requirements-windows.txt` 두 개만 운영합니다. `requirements.txt`는 사용하지 않습니다.
- 오디오 프리셋 기본값은 `core/audio/audio_presets.py`와 `dataset/audio_presets.json`을 같이 갱신합니다.
- STT 성능 기본값은 `prefetch_ahead`, `io_workers`, `stt_parallel_level`, `ff_threads`를 우선 확인합니다.
