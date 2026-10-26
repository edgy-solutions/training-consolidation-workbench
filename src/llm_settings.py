"""One resolver for the LLM endpoint; feeds both DSPy and BAML."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmSettings:
    provider: str  # "openai" or "ollama"
    base_url: str
    api_key: str
    model: str
    num_ctx: int


def _first(env, *names, default=""):
    for n in names:
        v = env.get(n)
        if v:
            return v
    return default


def llm_settings(env=None) -> LlmSettings:
    env = os.environ if env is None else env
    num_ctx = int(_first(env, "LLM_NUM_CTX", "OLLAMA_NUM_CTX", default="8192"))
    base = _first(env, "LLM_BASE_URL", "OPENAI_BASE_URL")
    if base:
        return LlmSettings(
            "openai",
            base.rstrip("/"),
            _first(env, "LLM_API_KEY", "OPENAI_API_KEY", default="any"),
            _first(env, "LLM_MODEL", "OPENAI_MODEL", "OLLAMA_MODEL", default="gpt-oss:120b"),
            num_ctx,
        )
    base = _first(env, "OLLAMA_BASE_URL", default="http://localhost:11434")
    base = base.removesuffix("/").removesuffix("/v1")
    return LlmSettings(
        "ollama",
        base,
        "",
        _first(env, "LLM_MODEL", "OLLAMA_MODEL", default="gpt-oss:120b"),
        num_ctx,
    )


def baml_client_options(s: LlmSettings) -> dict:
    opts = {
        "base_url": s.base_url if s.provider == "openai" else s.base_url + "/v1",
        "model": s.model,
    }
    if s.api_key:
        opts["api_key"] = s.api_key
    return opts


def baml_client_registry(s: LlmSettings | None = None):
    from baml_py import ClientRegistry

    s = s or llm_settings()
    cr = ClientRegistry()
    cr.add_llm_client(name="Llm", provider="openai-generic", options=baml_client_options(s))
    cr.set_primary("Llm")
    return cr
