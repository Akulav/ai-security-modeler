"""Application settings, read from the .env file in the data folder and the environment."""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Where the code is. The frontend build is served from here.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Where your map, settings and the LLM runtime live. The desktop launcher points this at its own
# folder, so updating the app never touches them. Run from source, it's the project folder.
DATA_ROOT = Path(os.environ.get("SECURITY_MODELER_HOME") or PROJECT_ROOT)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DATA_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(DATA_ROOT / 'data' / 'modeler.db').as_posix()}"

    # When on, the app installs and runs its own Ollama under llm/ on a free port, replacing
    # ollama_url at startup. Turn off to use the Ollama server at ollama_url instead.
    llm_auto_setup: bool = True
    ollama_version: str = "v0.40.13"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF"
    ollama_timeout_seconds: float = 1800
    ollama_num_ctx: int = 16384
    # The model leaves memory after this long without a request. 0 keeps it until it's unloaded.
    # This is the default; the analysis panel can change it.
    llm_idle_unload_seconds: int = 60

    hibp_api_key: str = ""
    hibp_base_url: str = "https://haveibeenpwned.com/api/v3"
    hibp_user_agent: str = "PersonalSecurityInfrastructureModeler"

    # Set by the desktop launcher, so only it can ask the app to quit.
    launcher_token: str = ""


settings = Settings()
