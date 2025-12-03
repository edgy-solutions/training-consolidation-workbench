
import dspy
import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()

def configure_dspy():
    """
    Configures the shared DSPy Language Model (LM) for the application.
    Returns the configured LM instance.
    """
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").replace('/v1', '')
    ollama_model = os.getenv("OLLAMA_MODEL", "gpt-oss:120b")
    
    print(f"[Config] Initializing shared DSPy LM: {ollama_base_url} -> {ollama_model}")
    
    lm = dspy.LM(model=f"ollama_chat/{ollama_model}", api_base=ollama_base_url, api_key="")
    dspy.configure(lm=lm)
    return lm

# Singleton instance
shared_lm = configure_dspy()
