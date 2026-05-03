<div align="center">

# AI Subtitle Studio

AI 기반 자막 생성, 자막 편집, 화자 분리, 멀티클립 처리, 러프컷 분석을 하나의 데스크톱 작업 흐름으로 연결하는 영상 자막 제작 도구입니다.

[![Version](https://img.shields.io/badge/version-v03.12.00-0A84FF?style=for-the-badge)](#)
[![Phase](https://img.shields.io/badge/phase-PHASE2-30D158?style=for-the-badge)](#)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![PyQt6](https://img.shields.io/badge/ui-PyQt6-41CD52?style=for-the-badge)](#)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-555?style=for-the-badge)](#)

<br />

[기능](#기능) · [빠른 시작](#빠른-시작) · [설치](#설치) · [프로젝트 구조](#프로젝트-구조) · [검증](#검증) · [릴리즈 노트](#릴리즈-노트) · [보안](#보안)

</div>

---

## 개요

AI Subtitle Studio는 긴 영상 작업에서 반복되는 자막 생성, 보정, 화자 구분, 멀티클립 관리, 러프컷 판단을 줄이기 위해 만든 데스크톱 앱입니다.

현재 저장소는 **PHASE2** 개발 단계이며, 러프컷 편집 엔진과 러프컷 UI를 중심으로 고도화하고 있습니다.

| 항목 | 내용 |
| --- | --- |
| 현재 버전 | `v03.12.00` |
| 개발 단계 | `PHASE2` |
| 기본 브랜치 | `main` |
| 지원 목표 | macOS, Windows |
| 주요 기술 | Python 3.11, PyQt6, Whisper, VAD, LLM, ffmpeg |

## 기능

### 자막 제작

- 영상/오디오 파일 기반 자막 생성
- Whisper 기반 STT 처리
- 기존 SRT 자동 로드 및 편집
- 자막 타이밍, 텍스트, 화자, 스타일 편집
- FHD/UHD 출력 기준 자막 스타일 preview
- 자막 품질 검사, 품질 필터, 후보 비교, 안전 조건 기반 자동 교정
- 확인 필요 자막은 타임라인 우클릭 메뉴에서 `자막 확정` 또는 `자막 삭제` 처리
- STT 앙상블 모드에서는 STT1/STT2 후보를 즉시 표시하고 최종 자막은 병합/LLM 분석 완료 후 반영
- 단일클립/멀티클립 모두 STT1/STT2 후보와 선택 메타데이터를 프로젝트 파일에 저장하고 재열기 때 복원
- 최종 자막세그먼트는 STT/LLM/VAD/화자 처리가 끝난 뒤 `간격` 설정의 자막간격 조정과 단일자막 유지 값을 마지막에 반영
- STT1/STT2 후보를 수동 선택한 작업은 Undo/Redo 스냅샷에 포함

### 편집 워크플로우

- 단일클립 / 멀티클립 작업
- 클립별 자막 저장 및 통합 자막 관리
- 타임라인 기반 세그먼트 편집
- 화자 분리 및 화자명 관리
- iCloud / NAS 자동 처리 감시

### 러프컷

- 자막 기반 챕터 분리
- 스토리 흐름 분석
- 컷 안전도 분석
- EDL JSON 생성
- Markdown 편집 가이드 생성
- retimed SRT 생성
- 렌더 계획 검증 및 실행 UI
- 자막 생성 완료 후 러프컷 초안 세그먼트를 먼저 생성하고 이후 AI/STT/LLM 메모리를 정리
- 긴 영상은 러프컷 초안 LLM 입력 제한을 넘으면 로컬 러프컷 세그먼트를 즉시 생성
- 사이드바 큐 리스트에서 각 항목의 완료 상태를 별도 상태 칸으로 표시

## 빠른 시작

macOS 기준:

```bash
git clone https://github.com/yongyeonyu/Ai-Subtitle-Studio.git
cd Ai-Subtitle-Studio

python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt

python main.py
```

Windows 기준:

```powershell
git clone https://github.com/yongyeonyu/Ai-Subtitle-Studio.git
cd Ai-Subtitle-Studio

python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-windows.txt

python main.py
```

## 설치

### 공통 요구사항

- Python `3.11`
- Git
- ffmpeg / ffprobe
- 충분한 디스크 공간
  - Whisper 모델, 중간 오디오, 렌더 결과 파일이 생성됩니다.

선택 요구사항:

- Ollama: 로컬 LLM 사용 시 필요
- Gemini API Key: Google Gemini 사용 시 필요
- OpenAI API Key: OpenAI 모델 사용 시 필요

### macOS

Apple Silicon Mac 기준으로 개발되고 있습니다.

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt
```

Homebrew로 ffmpeg 설치:

```bash
brew install ffmpeg
ffmpeg -version
ffprobe -version
```

앱 실행:

```bash
python main.py
```

### Windows

Windows 11 + Python 3.11 환경을 기준으로 합니다.

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
```

CUDA GPU를 사용할 경우 PyTorch CUDA 버전을 별도로 설치해야 할 수 있습니다.

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

winget으로 ffmpeg 설치:

```powershell
winget install Gyan.FFmpeg
ffmpeg -version
ffprobe -version
```

앱 실행:

```powershell
python main.py
```

또는 저장소에 포함된 `main.bat`을 사용할 수 있습니다.

## 설정

### LLM / API Key

앱은 로컬 LLM과 외부 API를 모두 고려합니다.

| Provider | 용도 |
| --- | --- |
| Ollama | 로컬 LLM 실행 |
| Gemini | 외부 LLM 보정 |
| OpenAI | 외부 LLM 보정 |

API Key와 Hugging Face Token은 설정의 `AI` 탭에서 입력하고 OS 보안 저장소에 저장합니다. 같은 `AI` 탭에서 STT1/STT2 Whisper 모델 선택, LLM 다운로드, Whisper/필수 모델 설치 상태 확인과 설치도 함께 관리합니다. API Key를 저장소에 직접 커밋하지 마세요.

### 출력물 / 로컬 데이터

대용량 영상, 캐시, 출력물, 프로젝트 개인 데이터는 GitHub에 올리지 않는 것을 원칙으로 합니다.

대표적인 로컬 데이터:

- `output/`
- `projects/`
- `dataset/user_settings.json`
- `dataset/folder_settings.json`
- `dataset/video_preview_cache/`

## 프로젝트 구조

```text
ai_subtitle_studio/
├── main.py                    # 앱 실행 진입점
├── config.py                  # 앱 버전, OS 감지, 기본 설정
├── requirements-mac.txt       # macOS 의존성
├── requirements-windows.txt   # Windows 의존성
├── core/                      # 자막, 오디오, 러프컷, 프로젝트 처리 로직
├── ui/                        # PyQt6 UI
├── tests/                     # unittest
├── assets/icons/              # 직접 수정 가능한 SVG 아이콘
├── dataset/                   # 설정/교정 데이터
├── output/                    # 중간 결과/출력 파일, GitHub 제외
└── projects/                  # 프로젝트 저장 파일, GitHub 제외
```

더 자세한 구조는 `File_structure.txt`를 참고하세요.

## 검증

기본 테스트:

```bash
venv/bin/python -m unittest discover -s tests
python3 -m py_compile main.py config.py
git diff --check
```

macOS에서 UI 생성 검증:

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python - <<'PY'
import sys
from PyQt6.QtWidgets import QApplication
from ui.main.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
print("MainWindow OK")
PY
```

## 문서

| 문서 | 설명 |
| --- | --- |
| `File_structure.txt` | 현재 파일 구조 |
| [`RELEASE_v03.12.00.md`](RELEASE_v03.12.00.md) | 최신 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.11.00.md`](RELEASE_v03.11.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.10.00.md`](RELEASE_v03.10.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.09.00.md`](RELEASE_v03.09.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.08.00.md`](RELEASE_v03.08.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.07.00.md`](RELEASE_v03.07.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.06.00.md`](RELEASE_v03.06.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.05.00.md`](RELEASE_v03.05.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.04.00.md`](RELEASE_v03.04.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.03.00.md`](RELEASE_v03.03.00.md) | 이전 PHASE2 릴리즈 노트 |
| [`RELEASE_v03.00.00.md`](RELEASE_v03.00.00.md) | PHASE2 누적 개발 노트 |
| `assets/icons/README.md` | SVG 아이콘 자산 규칙 |

개발 진행용 내부 문서인 `AGENTS.md`, `ACTION_ITEMS.md`, `check_list.md`는 로컬에서만 관리하고 GitHub에는 공개하지 않습니다.

## 릴리즈 노트

전체 최신 릴리즈 노트는 [`RELEASE_v03.12.00.md`](RELEASE_v03.12.00.md)를 참고하세요.

### 최신 릴리즈: v03.12.00

- 컷 경계 선발대/후발대 스캔을 분리해 시작 전에 임시 경계를 빠르게 수집하고, 후발대가 백그라운드에서 확정 경계를 검증합니다.
- 임시/확정 컷 경계와 회색 `주제없음` 중분류 세그먼트를 프로젝트와 editor_state에 저장하고 다시 열 때 복원합니다.
- STT1/STT2 preview 후보와 최종 자막은 저장된 임시/확정 컷 경계 근처에서 스냅되고, 확정 컷 경계는 절대 관통하지 않도록 유지합니다.
- STT1/STT2 후보 수동 선택은 겹치는 최종 자막을 잘라 교체하며, STT1↔STT2 선택 전환도 Undo/Redo 스냅샷으로 되돌릴 수 있습니다.
- 재시작 시 회색 중분류, 임시선, 확정선, 프로젝트 컷 경계 상태를 모두 비우고 처음 상태로 리셋합니다.
- 사이드바 버튼은 열려 있으면 초록 아이콘, 닫혀 있으면 기본 회색 아이콘으로 상태를 드러냅니다.
- Whisper 오디오 청크는 확정 컷 경계를 hard cut으로 사용하고, VAD 없는 fallback 경로에서도 컷 경계부터 다시 인식하도록 시작점을 재정렬합니다.

## 보안

공개 저장소에 올리면 안 되는 정보:

- API Key
- `.env`
- 개인 로컬 경로
- NAS 경로
- iCloud 개인 경로
- 작업 영상 원본
- 프로젝트 개인 데이터

실수로 키가 커밋된 경우 최신 파일에서 지우는 것만으로는 충분하지 않습니다. 해당 키를 폐기하고 새 키를 발급해야 하며, 필요하면 Git 이력 정리까지 진행해야 합니다.

## 개발 상태

이 프로젝트는 현재 개발 중입니다.

- PHASE1: 자막 생성, 편집, 화자 분리, 멀티클립 처리
- PHASE2: 러프컷 분석 및 편집 엔진
- PHASE3: 숏폼, API, 외부 연동, iPad 확장

## 라이선스

현재 별도 라이선스 파일이 포함되어 있지 않습니다.
