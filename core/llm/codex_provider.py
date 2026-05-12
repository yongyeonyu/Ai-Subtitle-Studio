# Version: 01.00.00
# Phase: PHASE2
"""Codex CLI provider for ChatGPT-plan subtitle LLM splitting."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


CODEX_MODEL_ALIASES = {
    "Codex ChatGPT [구독/CLI]",
    "OpenAI Codex ChatGPT [구독/CLI]",
    "OpenAI Codex [구독/CLI/API키 불필요]",
    "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]",
    "codex-chatgpt-cli",
}

DEFAULT_CODEX_LABEL = "OpenAI Codex ChatGPT [구독/CLI/API키 불필요]"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "result": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["result"],
    "additionalProperties": False,
}

_JSON_OBJECT_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
}


def is_codex_model(model_name: str) -> bool:
    text = str(model_name or "").strip()
    if not text:
        return False
    if text in CODEX_MODEL_ALIASES:
        return True
    lowered = text.lower()
    return "codex" in lowered and ("chatgpt" in lowered or "cli" in lowered or "구독" in text)


def codex_cli_available() -> tuple[bool, str]:
    explicit = str(os.environ.get("AI_SUBTITLE_CODEX_BIN", "") or "").strip()
    if explicit:
        expanded = os.path.expanduser(explicit)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return True, expanded
        return False, "AI_SUBTITLE_CODEX_BIN 경로를 확인해 주세요."
    found = shutil.which("codex")
    if found:
        return True, found
    return False, "Codex CLI를 찾을 수 없습니다. 설치 후 터미널에서 `codex`로 로그인해 주세요."


def _codex_binary() -> str:
    available, detail = codex_cli_available()
    if available:
        return detail
    raise RuntimeError(detail)


def _timeout(default: int) -> int:
    try:
        configured = int(float(os.environ.get("AI_SUBTITLE_CODEX_TIMEOUT", "") or 0))
    except Exception:
        configured = 0
    return max(1, configured or int(default or 120))


def _sandbox() -> str:
    value = str(os.environ.get("AI_SUBTITLE_CODEX_SANDBOX", "") or "read-only").strip()
    return value if value in {"read-only", "workspace-write"} else "read-only"


def _task_prompt(prompt: str) -> str:
    return (
        "You are AI Subtitle Studio's subtitle segmentation engine.\n"
        "Follow the user's subtitle-splitting prompt exactly.\n"
        "Return exactly one JSON object matching this schema:\n"
        '{"result": ["chunk 1", "chunk 2"]}\n'
        "Do not include markdown, code fences, explanations, comments, or extra fields.\n\n"
        f"{str(prompt or '').strip()}"
    )


def _extract_last_json_object(text: str) -> str | None:
    text = str(text or "")
    starts = [m.start() for m in re.finditer(r"\{", text)]
    for start in reversed(starts):
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
    return None


def _parse_chunks(output: str) -> list[str] | None:
    raw = str(output or "").strip()
    if not raw:
        return None
    candidates = [raw]
    recovered = _extract_last_json_object(raw)
    if recovered and recovered != raw:
        candidates.append(recovered)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        result = parsed.get("result")
        if not isinstance(result, list):
            continue
        chunks = [str(item).strip() for item in result if isinstance(item, str) and str(item).strip()]
        return chunks or None
    return None


def _parse_json_object(output: str) -> dict | None:
    raw = str(output or "").strip()
    if not raw:
        return None
    candidates = [raw]
    recovered = _extract_last_json_object(raw)
    if recovered and recovered != raw:
        candidates.append(recovered)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _command(codex_bin: str, schema_path: Path, output_path: Path) -> list[str]:
    cmd = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--color",
        "never",
        "--sandbox",
        _sandbox(),
        "--skip-git-repo-check",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
    ]
    model = str(os.environ.get("AI_SUBTITLE_CODEX_MODEL", "") or "").strip()
    if model:
        cmd.extend(["--model", model])
    effort = str(os.environ.get("AI_SUBTITLE_CODEX_EFFORT", "") or "").strip()
    if effort:
        cmd.extend(["--config", f'model_reasoning_effort="{effort}"'])
    return cmd


def _run_codex_json_task(
    model_name: str,
    prompt: str,
    *,
    schema: dict,
    timeout: int,
    task_prompt: str,
) -> str:
    if not is_codex_model(model_name):
        return ""
    codex_bin = _codex_binary()
    with tempfile.TemporaryDirectory(prefix="ai_subtitle_codex_") as tmp:
        tmpdir = Path(tmp)
        schema_path = tmpdir / "schema.json"
        output_path = tmpdir / "last_message.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        cmd = _command(codex_bin, schema_path, output_path)
        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(
                cmd,
                input=task_prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(tmpdir),
                env=env,
                timeout=_timeout(timeout),
                shell=False,
                **kwargs,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex CLI 실행 시간이 초과되었습니다.") from exc
        except OSError as exc:
            raise RuntimeError(f"Codex CLI 실행에 실패했습니다: {exc}") from exc

        stdout = str(proc.stdout or "")
        stderr = str(proc.stderr or "")
        if proc.returncode != 0:
            detail = (stderr or stdout or "no output").strip()[:800]
            raise RuntimeError(f"Codex CLI 인증 또는 실행에 실패했습니다: {detail}")

        output_text = ""
        try:
            if output_path.exists():
                output_text = output_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            output_text = ""
        if not output_text:
            output_text = stdout.strip()
        return output_text


def split_text(model_name: str, prompt: str, timeout: int = 120) -> list[str] | None:
    output_text = _run_codex_json_task(
        model_name,
        prompt,
        schema=_OUTPUT_SCHEMA,
        timeout=timeout,
        task_prompt=_task_prompt(prompt),
    )
    if not output_text:
        return None
    chunks = _parse_chunks(output_text)
    if chunks is None:
        raise RuntimeError("Codex 출력 파싱 실패: JSON result 배열을 찾지 못했습니다.")
    return chunks


def run_json(model_name: str, prompt: str, timeout: int = 180) -> dict | None:
    task_prompt = (
        "You are AI Subtitle Studio's roughcut planning engine.\n"
        "Follow the user's roughcut prompt exactly.\n"
        "Return exactly one JSON object. Do not include markdown, code fences, explanations, or comments.\n\n"
        f"{str(prompt or '').strip()}"
    )
    output_text = _run_codex_json_task(
        model_name,
        prompt,
        schema=_JSON_OBJECT_SCHEMA,
        timeout=timeout,
        task_prompt=task_prompt,
    )
    if not output_text:
        return None
    parsed = _parse_json_object(output_text)
    if parsed is None:
        raise RuntimeError("Codex 출력 파싱 실패: JSON object를 찾지 못했습니다.")
    return parsed
