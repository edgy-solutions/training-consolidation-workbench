import dspy
from dotenv import load_dotenv

from src.llm_settings import LlmSettings, llm_settings

# Load environment variables once
load_dotenv()


def build_lm(s: LlmSettings) -> dspy.LM:
    if s.provider == "openai":
        return dspy.LM(model=f"openai/{s.model}", api_base=s.base_url, api_key=s.api_key)
    return dspy.LM(model=f"ollama_chat/{s.model}", api_base=s.base_url, api_key="", num_ctx=s.num_ctx)


def configure_dspy():
    """
    Configures the shared DSPy Language Model (LM) for the application.
    Returns the configured LM instance.
    """
    s = llm_settings()
    print(f"[Config] Initializing shared DSPy LM: {s.provider} {s.base_url} -> {s.model} (ctx={s.num_ctx})")
    lm = build_lm(s)
    dspy.configure(lm=lm)
    return lm

# Singleton instance
shared_lm = configure_dspy()
