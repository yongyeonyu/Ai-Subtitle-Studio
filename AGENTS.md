# AI Subtitle Studio - Agent Customization Guide

This file helps AI agents understand the codebase, conventions, and language-specific design patterns in AI Subtitle Studio.

## Project Overview

**AI Subtitle Studio** is a PyQt6-based desktop application for automated subtitle generation, editing, and optimization for YouTube videos. It combines Whisper ASR, LLM-powered text correction, and speaker diarization.

**Key Language Focus**: Korean-first development with multi-language support architecture.

---

## 🌐 Language & Internationalization

### Core Language Configuration

- **Primary Language**: Korean (`ko`) — default in [config.py](config.py#L11)
- **Language Setting**: `LANGUAGE = "ko"` in `config` module
- **Secondary Support**: English (through translation features)
- **Encoding Standard**: UTF-8 (with fallbacks: cp949, euc-kr for legacy Korean text files)

### Language Usage Patterns

#### 1. **Configuration Level** ([config.py](config.py))
```python
LANGUAGE = "ko"  # Whisper model language parameter
WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx"  # Multilingual model
```
- Change `LANGUAGE` to support other Whisper-supported languages (`en`, `ja`, `zh`, etc.)
- See [media_processor.py](core/media_processor.py#L35) for how language is passed to Whisper

#### 2. **LLM Prompts & Rules** ([core/subtitle_engine.py](core/subtitle_engine.py))
- **System Prompt**: Hardcoded Korean-specific rules in `_HARDCODED_LLM_RULES`
- **User Prompt**: Loaded from [config.py](config.py#L16) as `DEFAULT_LLM_PROMPT` (Korean instructions)
- **Rules Content**: Lines 6, 70 specify language constraints: Korean & English only

**When Adding Languages**:
- Update LLM prompts in `config.py:DEFAULT_LLM_PROMPT` with language-specific rules
- Add language-aware rules to `_HARDCODED_LLM_RULES` in [subtitle_engine.py](core/subtitle_engine.py#L64)
- Update `_HALLUC_PHRASES` list (line 52) to include common non-translation outputs in the target language

#### 3. **UI Text** (All UI modules in `ui/` folder)
- **Current State**: All UI strings are hardcoded in Korean
- **Pattern**: No i18n framework (gettext, fluent, etc.) is currently used
- **Location Examples**:
  - [main_window.py](ui/main_window.py): Dialog titles, buttons, labels
  - [settings_*.py](ui/settings_dialog.py): Settings panel labels (AI, Advanced, Speaker, Gap, Export)
  - Editor widgets: Status messages, tooltips

**To Support Multiple UI Languages**:
1. Extract hardcoded strings to a centralized translation module
2. Consider a simple JSON-based i18n system (matching project's JSON-heavy config approach)
3. Alternative: Implement gettext support if more languages needed

#### 4. **Translation Features** ([core/worker_threads.py](core/worker_threads.py#L66))
- Built-in `_translate()` method supports English ↔ Korean translation
- Used for dictionary lookups and terminology assistance
- LLM-based (calls Ollama with language-specific prompts)

---

## 📝 Text Encoding Standards

### Multi-Encoding Support

The application handles legacy Korean subtitle files with fallback encoding:

```python
# From [editor_widget.py](ui/editor_widget.py#L423) and [main_window.py](ui/main_window.py#L752)
for enc in ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']:
    try:
        with open(srt_path, "r", encoding=enc) as f:
            content = f.read()
            break
    except:
        continue
```

- **utf-8-sig**: UTF-8 with BOM (byte order mark)
- **utf-8**: Modern standard
- **cp949**: Windows Korean code page (legacy)
- **euc-kr**: Unix Korean encoding (legacy)

**When Writing Files**:
- Always use `encoding="utf-8"` with `ensure_ascii=False` for JSON output
- Example: [main_window.py](ui/main_window.py#L111) saves settings as UTF-8 JSON

---

## 🛠️ Development Conventions

### Import & Module Paths

- **Base Path Setup**: [main.py](main.py#L7) adds BASE_DIR to `sys.path` before any core imports
- **Required**: Must happen before importing UI modules that depend on core

### Configuration Loading

- All JSON configs live in [dataset/](dataset/) folder
- Settings loaded at runtime, reflected immediately in UI
- Files: `user_settings.json`, `subtitle_rule.json`, `dataset_correction.json`
- See [subtitle_engine.py](core/subtitle_engine.py#L20-L29) for config loading patterns

### Worker Threads & LLM Integration

- LLM calls happen in [worker_threads.py](core/worker_threads.py) (non-blocking)
- Ollama server must be running: `exaone3.5:7.8b` (Korean-optimized model)
- Prompt engineering in `_translate()` method (lines 66-88) shows best practices for LLM interaction

---

## 🔤 Text Processing Rules

### Subtitle Optimization Rules ([core/subtitle_engine.py](core/subtitle_engine.py#L64-L87))

Critical hardcoded rules (must be language-aware when adapting):

1. **Punctuation Normalization**: Remove periods, add commas/tildes contextually
2. **Character Limits**: ~{threshold} characters per line (±5 char tolerance)
3. **Line Breaking**: Split at grammatically appropriate boundaries
4. **Language Constraint** (Line 70): Korean & English only — expand if supporting other languages
5. **Hallucination Prevention** (Line 52): Filter common transcription artifacts

### Correction Dictionary

- [dataset_correction.json](dataset/dataset_correction.json): Custom term mappings
- Loaded per-project for domain-specific corrections

---

## 🎯 When Working on Language-Related Features

### Checklist for Multi-Language Support

- [ ] Update `LANGUAGE` in [config.py](config.py#L11)
- [ ] Adapt LLM prompts in [config.py](config.py#L16) for target language grammar
- [ ] Extend `_HALLUC_PHRASES` in [subtitle_engine.py](core/subtitle_engine.py#L52) with target-language artifacts
- [ ] Test encoding with sample subtitle files from target language
- [ ] Update UI text if pursuing full i18n (currently all Korean)
- [ ] Verify Whisper model supports target language (`check model size/capabilities`)
- [ ] Update LLM rules (lines 6, 70) to reflect language constraints

### Testing Language Features

- Whisper accuracy: Test with sample audio in target language
- Encoding: Verify all subtitle file formats load correctly
- LLM output: Check prompt yields correct language in responses
- UI rendering: Ensure all text renders correctly (especially for CJK languages)

---

## 📚 Key Files for Language Work

| File | Purpose | Language-Related Lines |
|------|---------|----------------------|
| [config.py](config.py) | Global settings | 11, 16-22 (LANGUAGE, prompts) |
| [core/media_processor.py](core/media_processor.py) | Whisper integration | 35 (language param) |
| [core/subtitle_engine.py](core/subtitle_engine.py) | Text optimization | 52, 64, 70 (rules, constraints) |
| [core/worker_threads.py](core/worker_threads.py) | LLM translation | 66-88 (translation logic) |
| [ui/editor_widget.py](ui/editor_widget.py) | Subtitle editing | 423 (encoding handling) |
| [ui/main_window.py](ui/main_window.py) | Main UI | 752-754 (encoding), 111 (JSON save) |

---

## 🔍 Architecture Insights for Agents

### State & Pipeline

- State managed via FSM in [core/state_manager.py](core/state_manager.py)
- Pipeline flow in [ui/editor_pipeline.py](ui/editor_pipeline.py)
- Language/encoding decisions flow from config → media_processor → subtitle_engine

### Data Flow for Language Processing

1. **Input**: Audio file + language config
2. **ASR**: Whisper (language-specific model) → raw transcript
3. **LLM**: Ollama applies language-specific rules → optimized subtitle
4. **Output**: SRT file (UTF-8) with optimized text

### Common Gotchas

- No multi-language UI framework (all strings hardcoded Korean)
- LLM rules are language-specific; changing language without updating prompts causes failures
- Encoding fallback (cp949, euc-kr) handles legacy files; always write UTF-8
- Ollama model must match language (current: Korean-optimized exaone3.5)

---

## 📖 Related Documentation

- [Development Notes](development_notes.md) — Build commands, threading patterns, known issues
- [config.py](config.py) — All configurable language & LLM settings
- [requirements.txt](requirements.txt) — Dependencies (PyQt6, mlx-whisper, requests)

