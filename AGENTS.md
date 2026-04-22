# AGENTS.md — AI Subtitle Studio 개발 가이드

## 프로젝트 개요
- **AI Subtitle Studio**: macOS/Windows용 AI 기반 자막 생성 앱
- **Phase1**: STT + 자막 편집 (현재 개발 중)
- **Phase2**: Gemma4 등 AI로 러프컷 제작 (예정)
- **iPad**: 자막 에디터 중심 + 프리미엄 기능 (예정)

## 대표님 작업 스타일

### 개발 방식
- **create_all.py 패턴**: 수정사항을 Python 스크립트로 묶어서 한 번에 적용
  - 스크립트가 파일을 읽고 → 패치 적용 → 백업 생성 → 결과 출력
  - 알파벳 순서로 버전 관리: create_all.py → create_all_b.py → create_all_c.py ...
  - 한글 인코딩 이슈 → base64 또는 구조 기반 매칭 사용
- **단계적 리팩토링**: 폴더 이동 시 shim 파일로 하위 호환 유지
- **버전 헤더 통일**: 모든 .py 파일에 `# Version: XX.XX.XX` / `# Phase: PHASE1-B`

### 코드 원칙
- 모든 수정 파일은 헤더 버전 업데이트
- 폴더 이동 시 반드시 shim 생성 (기존 import 깨뜨리지 않음)
- Phase2를 고려한 폴더 구조 설계
- 파일 분할: 기능별로 300줄 이하 유지 목표

### 커뮤니케이션
- 호칭: "대표님"
- 한국어로 대화
- 코드 확인 후 수정 (grep/sed로 사전 확인 → 패치 생성)
- 검증: ast.parse로 문법 확인 필수

## 현재 폴더 구조 (v02.02.00)
```
ai_subtitle_studio/
├── core/
│   ├── pipeline/      ← 백엔드 파이프라인 (5파일)
│   ├── audio/         ← 오디오/Whisper (6파일)
│   └── (settings, utils, etc.)
├── ui/
│   ├── main/          ← 메인윈도우 (4파일)
│   ├── editor/        ← 에디터 (8파일)
│   ├── settings/      ← 설정 (7파일)
│   ├── timeline/      ← 타임라인 (9파일)
│   └── project/       ← 프로젝트 (4파일)
└── dataset/           ← 설정/학습 데이터 (JSON)
```

## 버전 규칙
- **앱 버전**: config.py `APP_VERSION`
- **파일 버전**: 각 .py 첫 줄 `# Version: XX.XX.XX`
- 기능 추가 → 중간 버전 (02.01.x → 02.02.x)
- 디버깅/안정화 → 패치 버전 (02.02.00 → 02.02.01)

## 주요 기술 스택
- Python 3.11
- PyQt6 (UI)
- MLX Whisper (macOS STT)
- faster-whisper (Windows STT)
- Ollama (로컬 LLM)
- Gemini API (클라우드 LLM)
- ffmpeg (오디오/비디오 처리)

## 테스트 환경
- macOS: MacBook Air (M-series, homebrew Python 3.11)
- Windows: 추후 진행 (CUDA, faster-whisper)

## 오늘 완료한 작업 (2026-04-23)
1. B1~B12 버그 수정 (멀티클립 오버레이, 큐 상태, 룰러, 웨이브폼 등)
2. F2/F3/F8/F9/F10/F12 기능 추가/확인
3. 전체 73개 파일 헤더 v02.02.00 통일
4. 폴더 구조 리팩토링 5단계 완료
   - core/pipeline/ (5파일)
   - ui/main/ (4파일)  
   - ui/settings/ (7파일)
   - ui/editor/ (8파일)
   - core/audio/ (6파일)
5. config.py APP_VERSION = "02.02.00"
