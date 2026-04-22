# 🎬 AI Subtitle Studio v02.02.00 Release Notes

**릴리즈 날짜:** 2026-04-23  
**Phase:** PHASE1-B  
**이전 버전:** v02.01.00

---

## ✨ 주요 변경 사항

### 📐 프로젝트 구조 전면 리팩토링

기존 플랫 구조에서 **Phase2 확장을 고려한 모듈화 구조**로 전환했습니다.

| 새 폴더 | 파일 수 | 역할 |
|---------|--------|------|
| `core/pipeline/` | 5 | 백엔드 파이프라인 (단일/멀티클립/헬퍼) |
| `core/audio/` | 6 | 오디오 추출 · Whisper · 화자 분리 |
| `core/engine/` | 1 | 자막 최적화 엔진 |
| `core/project/` | 2 | 프로젝트 저장/로드 |
| `ui/main/` | 4 | 메인윈도우 (시그널 · 파일 선택) |
| `ui/editor/` | 14 | 에디터 전체 (위젯 · 액션 · 세그먼트 · 비디오) |
| `ui/settings/` | 7 | 설정 다이얼로그 (AI · 화자 · 갭 · 출력) |
| `ui/dialogs/` | 2 | 내보내기 · 폴더 선택 |
| `ui/timeline/` | 9 | 타임라인 캔버스 · 페인트 · 입력 · 파형 |
| `ui/project/` | 4 | 멀티클립 · 프로젝트 패널 |

- **전체 73개 .py 파일** 헤더 `v02.02.00` 통일
- **23개 shim 파일** 생성 후 최종 제거 (직접 import 경로로 전환)
- `config.py` APP_VERSION = `"02.02.00"`

---

## 🐛 버그 수정 (12건)

| # | 내용 | 관련 파일 |
|---|------|----------|
| B1 | 멀티클립 그린존(VAD)/옐로우존(Whisper) 오버레이 미표시 | `backend`, `main_signals`, `timeline_canvas` |
| B2 | 음성인식 구간 파란 웨이브폼 미동작 | `timeline_canvas` (speech_mask 캐시 갱신) |
| B3 | 멀티클립 2/3/4번 클립 웨이브폼 미표시 | `multiclip_pipeline` (파형 로드 시점 이동) |
| B4 | 자막 추가 시 멀티클립 타임라인 자동 축소 안됨 | `timeline_widget` (fit_to_view 자동 호출) |
| B5 | 글로벌 캔버스 화면 벗어남 | `timeline_widget` (파형 완료 후 fit) |
| B6 | CLIP 라벨 위치 — 박스 우상단, 룰러 안 겹침 | `timeline_paint` (lbl_y=20) |
| B7 | 배치 모드 큐 상태 고착 + 다음 파일 전환 안됨 | `backend_fast` (명시적 완료 emit) |
| B8 | 큐 "완료" 시 소요시간/예상시간 미표시 | `queue_widget` (오디오 추출부터 추적) |
| B9 | 축소 시 룰러 숫자 겹침 | `timeline_paint` (nice_steps 확장) |
| B10 | 멀티클립 썸네일 파일명 가독성 | `multiclip_panel` (배경 + Bold) |
| B11 | 시작 버튼 시 웨이브폼 깜빡임 | `timeline_widget` (isRunning 가드) |
| B12 | 멀티클립 선택 시 SRT 파일 있으면 영상 1개만 로드 | `main_file_ops` (영상 우선 처리) |

---

## 🚀 기능 추가/개선 (6건)

| # | 내용 | 상세 |
|---|------|------|
| F2 | 빠른모드 Whisper medium 강제 적용 | `backend_fast.py` — LLM 단계 완전 제외 |
| F3 | ETA 모드별 독립 학습 | `FAST:` / `QUALITY:` 접두어로 EMA 분리 추적 |
| F8 | 자막 출력 시 dirty → 저장 확인 | 이미 구현 확인 (editor_actions.py) |
| F9 | 인라인 편집 바깥 클릭 → 커밋 | 이미 구현 확인 (timeline_input.py) |
| F10 | 타임라인 하단 여백 축소 | `CANVAS_H` 22 → 6 (글로벌 캔버스 밀착) |
| F12 | 멀티클립 버튼 "(N개)" 개수 표시 제거 | `multiclip_panel.py` — 깔끔한 버튼 텍스트 |

---

## 🔧 중요 버그 수정 (추가)

- **중복 transcribe 루프 제거**: `multiclip_pipeline.py`에서 Whisper transcribe가 2회 실행되던 버그 수정
- **BOM 문자 제거**: `project_panel.py`의 U+FEFF 문자 제거
- **상대 import 수정**: `subtitle_engine.py` 폴더 이동 후 `from .utils` → `from core.utils`

---

## 📊 변경 통계

| 항목 | 수치 |
|------|------|
| 수정된 파일 | 73+ |
| 새로 생성된 파일 | 30+ (폴더 이동 포함) |
| 삭제된 shim 파일 | 23 |
| 새 폴더 | 8 (`pipeline`, `audio`, `engine`, `project`, `main`, `editor`, `settings`, `dialogs`) |
| 총 코드 라인 | ~17,000 |

---

## 📁 최종 폴더 구조

```
ai_subtitle_studio/
├── main.py · config.py · logger.py
├── core/
│   ├── pipeline/      ← 백엔드 파이프라인 (5)
│   ├── audio/         ← 오디오/Whisper (6)
│   ├── engine/        ← 자막 엔진 (1)
│   ├── project/       ← 프로젝트 관리 (2)
│   └── (settings, utils, etc.)
├── ui/
│   ├── main/          ← 메인윈도우 (4)
│   ├── editor/        ← 에디터 (14)
│   ├── settings/      ← 설정 (7)
│   ├── timeline/      ← 타임라인 (9)
│   ├── project/       ← 프로젝트 UI (4)
│   └── dialogs/       ← 다이얼로그 (2)
└── dataset/           ← 설정/학습 JSON
```

---

## 📝 문서

- `STRUCTURE.txt` — v02.02.00 기준 전체 파일 구조 + 변경이력
- `AGENTS.md` — 개발 가이드 (작업 스타일, 기술 스택, create_all 패턴)

---

## 🔮 다음 버전 예고 (PHASE2)

- F1: 상황별 오디오 프리셋 (6~8개 기본 + 커스텀)
- F4: NTFY 알림 설정 UI
- F5: 도움말 시스템
- F11: 에디터 클립 추가 [+] + 드래그 순서 변경
- R3: AI 모델 관리 시스템 (Windows)
- R4: Windows 전기능 연동 (faster-whisper, CUDA)
