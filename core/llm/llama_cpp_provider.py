from __future__ import annotations

from typing import Any


def llama_cpp_available() -> bool:
    try:
        import llama_cpp  # noqa: F401

        return True
    except Exception:
        return False


def is_llama_cpp_model(model: str) -> bool:
    text = str(model or "").strip().lower()
    return text.startswith("llama_cpp:") or text.endswith(".gguf")


def normalize_llama_cpp_model_path(model: str) -> str:
    raw = str(model or "").strip()
    if raw.lower().startswith("llama_cpp:"):
        raw = raw.split(":", 1)[1].strip()
    return raw


def generate_text(
    model: str,
    prompt: str,
    *,
    timeout: float | int = 180,
    num_predict: int = 1024,
    temperature: float = 0.2,
    json_format: bool = True,
) -> str:
    _ = timeout
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as exc:
        raise RuntimeError("llama_cpp_python_unavailable") from exc
    model_path = normalize_llama_cpp_model_path(model)
    if not model_path:
        raise RuntimeError("llama_cpp_model_path_missing")
    kwargs: dict[str, Any] = {
        "model_path": model_path,
        "n_ctx": 4096,
        "n_threads": 0,
        "verbose": False,
    }
    llm = Llama(**kwargs)
    suffix = "\nReturn only one valid JSON object." if json_format else ""
    response = llm(
        str(prompt or "") + suffix,
        max_tokens=max(16, int(num_predict or 1024)),
        temperature=float(temperature or 0.0),
        echo=False,
    )
    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        return ""
    return str(dict(choices[0]).get("text") or "")


__all__ = [
    "generate_text",
    "is_llama_cpp_model",
    "llama_cpp_available",
    "normalize_llama_cpp_model_path",
]
