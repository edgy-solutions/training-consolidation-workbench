from src.llm_settings import baml_client_options, llm_settings


def test_ollama_default():
    s = llm_settings({})
    assert (s.provider, s.base_url, s.api_key, s.model, s.num_ctx) == (
        "ollama", "http://localhost:11434", "", "gpt-oss:120b", 8192)


def test_ollama_v1_suffix_stripped_only_at_end():
    assert llm_settings({"OLLAMA_BASE_URL": "http://h:1/v1"}).base_url == "http://h:1"
    assert llm_settings({"OLLAMA_BASE_URL": "http://h:1/v1/"}).base_url == "http://h:1"
    assert llm_settings({"OLLAMA_BASE_URL": "http://h/v1x/api"}).base_url == "http://h/v1x/api"


def test_llm_base_url_wins():
    s = llm_settings({"LLM_BASE_URL": "http://a/v1/", "OPENAI_BASE_URL": "http://b/v1",
                      "OLLAMA_BASE_URL": "http://c"})
    assert (s.provider, s.base_url) == ("openai", "http://a/v1")


def test_openai_fallbacks_and_empty_unset():
    s = llm_settings({"LLM_BASE_URL": "", "OPENAI_BASE_URL": "http://b/v1",
                      "OPENAI_API_KEY": "k", "OPENAI_MODEL": "m", "OLLAMA_MODEL": "o"})
    assert (s.provider, s.base_url, s.api_key, s.model) == ("openai", "http://b/v1", "k", "m")


def test_openai_key_default_and_model_precedence():
    s = llm_settings({"LLM_BASE_URL": "http://a", "OLLAMA_MODEL": "o"})
    assert (s.api_key, s.model) == ("any", "o")
    assert llm_settings({"LLM_MODEL": "l", "OLLAMA_MODEL": "o"}).model == "l"


def test_num_ctx_precedence():
    assert llm_settings({"OLLAMA_NUM_CTX": "4096"}).num_ctx == 4096
    assert llm_settings({"LLM_NUM_CTX": "1000", "OLLAMA_NUM_CTX": "4096"}).num_ctx == 1000


def test_baml_client_options():
    o = llm_settings({"OLLAMA_BASE_URL": "http://h:1", "OLLAMA_MODEL": "m"})
    assert baml_client_options(o) == {"base_url": "http://h:1/v1", "model": "m"}
    p = llm_settings({"LLM_BASE_URL": "http://a/v1", "LLM_API_KEY": "k", "LLM_MODEL": "m"})
    assert baml_client_options(p) == {"base_url": "http://a/v1", "api_key": "k", "model": "m"}


def test_build_lm_models():
    from src.dspy_modules.config import build_lm
    assert build_lm(llm_settings({"LLM_BASE_URL": "http://a/v1", "LLM_MODEL": "m"})).model == "openai/m"
    assert build_lm(llm_settings({"OLLAMA_MODEL": "m"})).model == "ollama_chat/m"
