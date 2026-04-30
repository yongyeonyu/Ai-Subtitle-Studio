# AI Subtitle Studio

AI Subtitle Studio는 영상/오디오 파일에서 자막을 생성하고, 자막 편집, 화자 분리, 멀티클립 처리, 러프컷 편집까지 한 화면에서 진행하기 위한 데스크톱 앱입니다.

현재 개발 단계는 **PHASE2**이며, 러프컷 편집 엔진과 러프컷 UI를 고도화하고 있습니다.

- 현재 버전: `v03.01.14`
- 기본 브랜치: `main`
- 지원 목표: macOS / Windows
- 주요 기술: Python 3.11, PyQt6, Whisper, VAD, LLM, ffmpeg

## 주요 기능

- 영상/오디오 파일 열기
- Whisper 기반 자막 생성
- 자막 편집 및 SRT 저장
- 화자 분리 및 화자명 관리
- 단일클립 / 멀티클립 작업
- iCloud / NAS 자동 처리 감시
- 자막 스타일 설정 및 동영상 출력
- PHASE2 러프컷 분석
  - 챕터 분리
  - 컷 안전도 분석
  - EDL JSON 생성
  - Markdown 편집 가이드 생성
  - retimed SRT 생성
  - 렌더 계획 검증 및 실행 UI

## 저장소 보기 권한

이 저장소는 GitHub에서 `public`으로 공개되어 있습니다.

따라서 아래 주소를 아는 사람은 브라우저에서 프로젝트 설명, 코드, 커밋 이력, 문서를 확인할 수 있습니다.

[https://github.com/yongyeonyu/Ai-Subtitle-Studio](https://github.com/yongyeonyu/Ai-Subtitle-Studio)

## 공통 요구사항

- Python `3.11`
- Git
- ffmpeg / ffprobe
- 충분한 디스크 공간
  - Whisper 모델, 중간 오디오, 렌더 결과 파일이 생성됩니다.
- 선택 사항
  - Ollama: 로컬 LLM 사용 시 필요
  - Gemini / OpenAI API Key: 외부 LLM 사용 시 필요

## macOS 설치 및 실행

Apple Silicon Mac 기준으로 개발되고 있습니다.

### 1. 저장소 받기

```bash
git clone https://github.com/yongyeonyu/Ai-Subtitle-Studio.git
cd Ai-Subtitle-Studio
```

### 2. Python 가상환경 만들기

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
```

### 3. 패키지 설치

```bash
pip install -r requirements-mac.txt
```

### 4. ffmpeg 설치

Homebrew를 사용하는 경우:

```bash
brew install ffmpeg
```

설치 확인:

```bash
ffmpeg -version
ffprobe -version
```

### 5. 앱 실행

```bash
python main.py
```

## Windows 설치 및 실행

Windows 11 + Python 3.11 환경을 기준으로 합니다.

### 1. 저장소 받기

```powershell
git clone https://github.com/yongyeonyu/Ai-Subtitle-Studio.git
cd Ai-Subtitle-Studio
```

### 2. Python 가상환경 만들기

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3. 패키지 설치

```powershell
pip install -r requirements-windows.txt
```

CUDA GPU를 사용할 경우 PyTorch CUDA 버전을 별도로 설치해야 할 수 있습니다.

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 4. ffmpeg 설치

Windows에서는 아래 중 하나를 사용할 수 있습니다.

- winget
- Chocolatey
- ffmpeg 공식 빌드 직접 설치

winget 예시:

```powershell
winget install Gyan.FFmpeg
```

설치 후 새 터미널을 열고 확인합니다.

```powershell
ffmpeg -version
ffprobe -version
```

### 5. 앱 실행

```powershell
python main.py
```

또는 저장소에 있는 `main.bat`을 사용할 수 있습니다.

## LLM / API 설정

앱은 로컬 LLM과 외부 API를 함께 고려합니다.

- Ollama: 로컬 LLM 사용
- Gemini API Key: Google Gemini 사용
- OpenAI API Key: OpenAI 모델 사용

API Key는 앱 설정 화면에서 입력하는 흐름을 기준으로 합니다. 운영 중인 API Key를 GitHub에 직접 올리지 마세요.

## 주요 폴더

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
├── output/                    # 중간 결과/출력 파일
└── projects/                  # 프로젝트 저장 파일
```

더 자세한 구조는 `File_structure.txt`를 참고하세요.

## 테스트 / 검증

개발 중 기본 검증 명령은 아래와 같습니다.

```bash
venv/bin/python -m unittest discover -s tests
python3 -m py_compile main.py config.py
git diff --check
```

macOS에서 UI 생성 검증을 할 때는 다음처럼 offscreen 모드를 사용할 수 있습니다.

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

## 참고 문서

- `AGENTS.md`: 개발 원칙, 작업 인수인계, 다음 작업 프롬프트
- `ACTION_ITEMS.md`: 남은 구현 항목
- `check_list.md`: 확인 체크리스트
- `File_structure.txt`: 현재 파일 구조
- `RELEASE_v03.00.00.md`: PHASE2 릴리즈 노트

## 주의사항

- 이 프로젝트는 현재 개발 중인 데스크톱 앱입니다.
- 대용량 영상, 캐시, 출력물은 GitHub에 올리지 않는 것을 원칙으로 합니다.
- API Key, 개인 경로, NAS 경로, iCloud 경로 등 민감 정보는 커밋하지 마세요.
- macOS와 Windows는 Whisper 백엔드가 다르므로 설치 패키지와 실행 성능이 다를 수 있습니다.
