<div align="center">

# AI Subtitle Studio

Accuracy-first desktop subtitle production for long-form video, rough cuts, speaker-aware editing, and repeatable subtitle workflows.

[![App Version](https://img.shields.io/badge/app-03.24.03-0A84FF?style=for-the-badge)](#)
[![Release](https://img.shields.io/badge/release-v03.24.03-30D158?style=for-the-badge)](RELEASE_v03.24.03.md)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![PyQt6](https://img.shields.io/badge/ui-PyQt6-41CD52?style=for-the-badge)](#)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-555?style=for-the-badge)](#)

</div>

## Purpose

AI Subtitle Studio is built for one primary outcome: produce highly accurate subtitles on the first pass, even when that takes longer than a fast draft. The goal is to reduce manual correction time by combining STT, audio preprocessing, VAD, cut-boundary alignment, LLM cleanup, subtitle timing rules, LoRA personalization, and project-aware editing in one desktop workflow.

Current development has completed the v03.24.03 Editor Performance release. The app keeps one user-facing Mode control: `Fast`, `Auto`, `High`, and `STT 모드`, while improving editor responsiveness with lookup-backed subtitle sync, vector-style timeline rendering caches, safer model/runtime cleanup after generation, and benchmark-driven CPU/GPU/NPU scheduling defaults.

## Core Workflows

- Single-file subtitle generation and editing.
- Folder queue processing, where selected files are listed and processed individually in sequence.
- Multiclip editing when explicitly selected from multiclip flows.
- iCloud and NAS background processing.
- Fast/Auto/High Mode policy shared across single-file, multiclip, folder queue, iCloud, and NAS workflows.
- Subtitle tool stack policy: Fast = LoRA, Auto = LoRA + Deep Learning, High = LoRA + Deep Learning + LLM, STT Mode = VAD + human input + LoRA/Deep/rules.
- STT Mode portable project state: `stt_mode_state` keeps VAD work segments, raw dictation, rolling windows, and final subtitle mirrors separate from the normal vector subtitle canvas.
- STT Mode iPad compatibility scope is intentionally limited to project state and STT LoRA/runtime policy bundles; this repository does not implement an iPad app.
- Stable editor text, video, and timeline render frames with frame-based or whole-editor GPU rendering policy.
- Fast editor-mode subtitle movement using line-map caches, dirty-rectangle timeline updates, visible-window video context refreshes, and non-jittery active-segment scrolling.
- Ten-step engine dashboard: cut boundary, preprocessing, audio filter, STT1, STT2, VAD, subtitle LLM, roughcut LLM, LoRA, and deep learning.
- Runtime sidebar display of the current file's automatic audio-filter and VAD choices.
- Process-level project JSON caching plus safe atomic project and settings writes.
- STT1/STT2 candidate comparison with persistent project metadata.
- Cut-boundary assisted subtitle timing.
- Accuracy-first audio routing with clip or chunk-level preprocessing decisions.
- Roughcut draft generation from subtitle and scene structure.
- Subtitle video output after subtitle generation.
- Text, voice, multimodal, STT1 adapter, and settings LoRA personalization data management, including idle-only background learning, Full learning controls, detailed learning logs, and automatic gap/bundle/context policies.
- STT LoRA/runtime bundle export writes policy-json bundles with protected terms, VAD boundary policy, dictation resegmentation policy, and manifest/checksum metadata for future desktop/iPad reuse.

All core algorithms should be shared across single-file, multiclip, folder queue, iCloud, and NAS modes.

## Quick Start

macOS:

```bash
python3.11 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-mac.txt
python main.py
```

Windows:

```powershell
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-windows.txt
python main.py
```

Required runtime tools:

- Python 3.11
- ffmpeg and ffprobe
- Git
- Sufficient disk space for models, temporary audio, project files, and render output

Optional tools:

- Ollama for local LLM workflows.
- Hugging Face token for some model downloads.
- External LLM API keys when enabled in settings.

## Project Data

Local runtime data is intentionally not treated as source code.

Typical local data:

- `output/`
- `projects/`
- `dataset/user_settings.json`
- `dataset/folder_settings.json`
- `dataset/video_preview_cache/`
- `dataset/lora_personalization/`

Do not commit private media, generated output, API keys, NAS paths, iCloud paths, or user project data.

## Handoff Documents

The repository uses five handoff documents for continuation between chats:

| File | Role |
| --- | --- |
| `AGENTS.md` | Agent bootstrap rules and release-handoff rules. |
| `ACTION_ITEMS.md` | Remaining work queue only. |
| `File_structure.txt` | Actual project tree only. |
| `README.md` | Product purpose, setup, and current direction. |
| `RELEASE_v*.md` | One release note, based only on the immediately previous release. |

If a new chat receives only `AGENTS.md`, the assistant must find and read the other four files automatically.

## Current State

| Item | Value |
| --- | --- |
| App version in code | `03.24.03` |
| Latest release checkpoint | `v03.24.03` |
| Handoff document version | `03.24.03` |
| Active phase | `EDITOR_PERFORMANCE_RELEASED` |
| Next planned phase | None |
| Product priority | Accuracy before speed |
| Supported target platforms | macOS and Windows |

## Verification

Common development checks:

```bash
venv/bin/python -m pytest -q
venv/bin/python -m compileall -q main.py core ui tests
git diff --check -- .
```

For UI smoke testing without showing a window:

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

## Release Notes

The current release checkpoint is [`RELEASE_v03.24.03.md`](RELEASE_v03.24.03.md). Older release notes remain in the repository as history, but handoff documents should only summarize the latest state and the immediately previous release relationship.

## Security

Never commit:

- API keys
- `.env` secrets
- private media
- private project files
- NAS paths
- personal iCloud paths
- generated subtitle/render output

If a secret is committed, remove it from the provider side and rotate it. Removing it from the latest file is not enough.
