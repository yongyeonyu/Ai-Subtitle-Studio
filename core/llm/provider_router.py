from __future__ import annotations

from typing import Any

from core.llm.openai_provider import is_openai_model


def normalize_llm_provider(provider: str, model: str = "") -> str:
    key = str(provider or "").strip().lower()
    model_text = str(model or "").strip()
    if key in {"llamacpp", "llama.cpp", "llama_cpp", "gguf"}:
        return "llama_cpp"
    if key in {"gemini"}:
        return "google"
    if key:
        return key
    try:
        from core.llm.llama_cpp_provider import is_llama_cpp_model

        if is_llama_cpp_model(model_text):
            return "llama_cpp"
    except Exception:
        pass
    if is_openai_model(model_text):
        return "openai"
    return "ollama"


def generate_text(
    provider: str,
    model: str,
    prompt: str,
    *,
    timeout: int = 180,
    num_predict: int = 1024,
    temperature: float = 0.2,
    json_format: bool = True,
    attempts: int = 1,
) -> str:
    provider_key = normalize_llm_provider(provider, model)
    if provider_key == "llama_cpp":
        from core.llm.llama_cpp_provider import generate_text as generate_llama_cpp

        return generate_llama_cpp(
            model,
            prompt,
            timeout=timeout,
            num_predict=num_predict,
            temperature=temperature,
            json_format=json_format,
        )
    if provider_key == "ollama":
        from core.llm.ollama_provider import generate_text as generate_ollama

        return generate_ollama(
            model,
            prompt,
            timeout=timeout,
            keep_alive=-1,
            num_predict=num_predict,
            temperature=temperature,
            json_format=json_format,
            attempts=attempts,
        )
    raise RuntimeError(f"unsupported_local_llm_provider:{provider_key}")


def local_llm_provider_available(provider: str, model: str = "") -> bool:
    provider_key = normalize_llm_provider(provider, model)
    if provider_key == "llama_cpp":
        try:
            from core.llm.llama_cpp_provider import llama_cpp_available

            return llama_cpp_available()
        except Exception:
            return False
    if provider_key == "ollama":
        return True
    return False


__all__ = ["generate_text", "local_llm_provider_available", "normalize_llm_provider"]
