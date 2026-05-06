<div align="center">

# AI Subtitle Studio

Accuracy-first desktop subtitle production for long-form video, rough cuts, speaker-aware editing, and repeatable subtitle workflows.

[![App Version](https://img.shields.io/badge/app-03.21.00-0A84FF?style=for-the-badge)](#)
[![Release](https://img.shields.io/badge/release-v03.21.00-30D158?style=for-the-badge)](RELEASE_v03.21.00.md)
[![Python](https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![PyQt6](https://img.shields.io/badge/ui-PyQt6-41CD52?style=for-the-badge)](#)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-555?style=for-the-badge)](#)

</div>

## Purpose

AI Subtitle Studio is built for one primary outcome: produce highly accurate subtitles on the first pass, even when that takes longer than a fast draft. The goal is to reduce manual correction time by combining STT, audio preprocessing, VAD, cut-boundary alignment, LLM cleanup, subtitle timing rules, and project-aware editing in one desktop workflow.

Current development has completed the v03.21.00 accuracy automation and tablet-readiness checkpoint. The current release turns the subtitle pipeline into a decision-and-verification workflow: media cache keys use fingerprints instead of filenames, STT alternatives are retained as candidate lattices, LoRA/deep-learning policies apply subtitle-specific settings, LLM output is constrained and verified before commit, dynamic schedulers tune workload to the machine, recovery state is safer after app restarts, and iPad/tablet UI scaffolding is ready without changing desktop behavior.

## Core Workflows

- Single-file subtitle generation and editing.
- Folder queue processing, where selected files are listed and processed individually in sequence.
- Multiclip editing when explicitly selected from multiclip flows.
- iCloud and NAS background processing.
- STT1/STT2 candidate comparison with persistent project metadata.
- Cut-boundary assisted subtitle timing.
- Accuracy-first audio routing with clip or chunk-level preprocessing decisions.
- Roughcut draft generation from subtitle and scene structure.
- Subtitle video output after subtitle generation.
- GPU/QML timeline, overlay, editor, settings, and project-panel migration foundations.
- Text, voice, multimodal, STT1 adapter, and settings LoRA personalization data management, including LLM review JSON exchange, transcript-aligned WAV clip manifests, quality-tier LoRA bundles, vectorized runtime retrieval, subtitle-specific settings autopilot, Full learning controls, idle-only background learning, detailed learning logs, and automatic gap/bundle/context policies.

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
| App version in code | `03.21.00` |
| Latest release checkpoint | `v03.21.00` |
| Handoff document version | `03.21.00` |
| Active phase | `COMPLETE` |
| Next planned phase | None |
| Product priority | Accuracy before speed |
| Supported target platforms | macOS and Windows |

## Verification

Common development checks:

```bash
venv/bin/python -m pytest -q
python3 -m compileall -q main.py core ui tests
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

The current release checkpoint is [`RELEASE_v03.21.00.md`](RELEASE_v03.21.00.md). Older release notes remain in the repository as history, but handoff documents should only summarize the latest state and the immediately previous release relationship.

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
