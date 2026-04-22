# AGENTS.md — AI Subtitle Studio 개발 가이드

## 프로젝트 개요
- **AI Subtitle Studio**: macOS/Windows용 AI 기반 자막 생성 및 편집 앱
- **개발자**: 대표님
- **AI 어시스턴트**: Microsoft Copilot (코드 생성 + create_all 스크립트 기반 패치)

---

## 🎯 최종 목표

### 1. macOS/Windows 데스크탑 앱
- **Phase1**: STT + 자막 편집 (현재 개발 중, PHASE1-B)
- **Phase2**: Gemma4 등 AI로 **자동 러프컷 편집** — 최종 목표는 영상 자막 생성부터 컷편집까지 원스톱 자동화

### 2. iPad 앱 (유료 출시 예정)
- 자막 에디터 중심의 모바일 앱
- 프리미엄 기능: **Whisper STT + LLM 자막 최적화**
- 무료: 자막 편집/타이밍 조정
- 유료: AI 자막 생성 (Whisper) + LLM 문장 최적화 + 자동 화자 분리

---

## 🖥️ 개발 환경

### 회사 (Windows)
- Windows 11 + CUDA GPU
- Python 3.11 + faster-whisper (CUDA 가속)
- 주로 R3(AI 모델 관리), R4(Windows 전기능) 작업
- faster-whisper subprocess worker 기반

### 집 (macOS)
- MacBook Air (Apple Silicon, M-series)
- Python 3.11 (homebrew) + MLX Whisper
- 주로 UI/UX 개발, 리팩토링, 버그 수정
- MLX persistent worker 기반 (모델 1회 로드 후 재사용)

### 공통
- PyQt6 (크로스 플랫폼 UI)
- Ollama (로컬 LLM) / Gemini API (클라우드 LLM)
- ffmpeg (오디오/비디오 처리)
- Git (main 브랜치 단일 운영)

---

## 🔧 코드 수정 방식: create_all 스크립트 패턴

### 원칙
**모든 코드 수정은 Python 스크립트(`create_all_X.py`)로 수행합니다.**
수동 편집은 하지 않으며, 스크립트가 파일을 읽고 → 패치 적용 → 백업 생성 → 결과 출력합니다.

### 장점
1. **실수 방지** — 수십 개 파일 수동 수정 시 빠뜨리기 쉬운 부분을 스크립트가 정확하게 처리
2. **재현 가능** — 같은 스크립트를 다시 돌려도 동일한 결과
3. **자동 백업** — 매 실행 시 `_backup_X_날짜/` 폴더에 원본 보관
4. **한 눈에 검증** — `[OK]`, `[WARN]`, `[SKIP]` 태그로 즉시 확인
5. **AST 문법 검사** — 스크립트 생성 시 `ast.parse()`로 사전 검증

### 스크립트 명명 규칙
```
create_all.py    → 첫 번째 대규모 변경 (파일 생성/분할)
create_all_b.py  → 두 번째 패치 (버그 수정)
create_all_c.py  → 세 번째 패치
...
create_all_i.py  → 아홉 번째 패치
```

### 스크립트 구조
```python
#!/usr/bin/env python3
def main():
    # 1) 백업 디렉토리 생성
    # 2) 파일 읽기 → 패턴 매칭 → 치환
    # 3) 결과 출력 [OK] / [WARN]
    
if __name__ == "__main__":
    main()
```

### 한글 인코딩 주의
- 스크립트 내 한글 문자열 매칭 시 인코딩 깨짐 문제 발생 가능
- **해결책**: 구조 기반 매칭 (한글이 아닌 코드 패턴으로 탐색) 또는 base64 인코딩

---

## 📁 폴더 구조 (v02.02.00)

```
ai_subtitle_studio/
├── main.py · config.py · logger.py
├── core/
│   ├── pipeline/      ← 백엔드 파이프라인 (5파일)
│   ├── audio/         ← 오디오/Whisper (6파일)
│   ├── engine/        ← 자막 엔진 (1파일)
│   ├── project/       ← 프로젝트 관리 (2파일)
│   └── (settings, utils, path_manager, etc.)
├── ui/
│   ├── main/          ← 메인윈도우 (4파일)
│   ├── editor/        ← 에디터 (14파일)
│   ├── settings/      ← 설정 (7파일)
│   ├── timeline/      ← 타임라인 (9파일)
│   ├── project/       ← 프로젝트 UI (4파일)
│   └── dialogs/       ← 다이얼로그 (2파일)
└── dataset/           ← 설정/학습 데이터 (JSON)
```

---

## 📐 코드 원칙

1. **헤더 통일**: 모든 .py 파일에 `# Version: XX.XX.XX` / `# Phase: PHASE1-B`
2. **파일 크기**: 기능별 분할, 300줄 이하 유지 목표
3. **폴더 이동 시**: shim 파일 → 안정화 확인 → shim 제거 + 직접 import
4. **Phase2 고려**: 폴더 구조는 향후 자동 편집 기능 추가를 고려해 설계
5. **Whisper 모델**: 사용자가 large-v3를 선택한 경우 절대 자동 다운그레이드 금지

---

## 📌 버전 규칙

- **앱 버전**: `config.py` → `APP_VERSION`
- **파일 버전**: 각 .py 첫 줄 `# Version: XX.XX.XX`
- 기능 추가 → 중간 버전 (02.01.x → 02.02.x)
- 디버깅/안정화 → 패치 버전 (02.02.00 → 02.02.01)
- PHASE1-B 기준 버전은 02.00.00부터 시작

---

## ✅ v02.02.00 완료 내역 (2026-04-22~23)

### 버그 수정 12건 (B1~B12)
- 멀티클립 오버레이, 웨이브폼, 큐 상태, 룰러, 썸네일 등

### 기능 추가 6건 (F2/F3/F8/F9/F10/F12)
- 빠른모드 Whisper medium 강제, ETA 모드별 분리 등

### 인프라 리팩토링
- 폴더 구조 8개 신규 (pipeline, audio, engine, project, main, editor, settings, dialogs)
- 73개 파일 헤더 v02.02.00 통일
- 23개 shim 파일 생성 → 안정화 후 삭제
- STRUCTURE.txt + AGENTS.md + RELEASE_v02.02.00.md 문서 추가

---

## 🔮 앞으로 남은 작업

### PHASE1-B 잔여
- R3: AI 모델 관리 시스템 (Windows 환경)
- R4: Windows 전기능 연동 (faster-whisper, CUDA)

### PHASE2 예정
- F1: 상황별 오디오 프리셋
- F4: NTFY 알림 설정 UI
- F5: 도움말 시스템
- F11: 에디터 클립 추가 + 드래그 순서 변경
- **자동 러프컷 편집 (Gemma4 등 AI 기반)**

### iPad 앱
- 자막 에디터 UI (SwiftUI)
- Whisper STT + LLM 최적화 (프리미엄)
- App Store 유료 출시
