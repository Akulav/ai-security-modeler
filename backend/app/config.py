"""Application settings, read from the project-root .env file and the environment."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'modeler.db').as_posix()}"

    # When on, the app installs and runs its own Ollama under llm/ on a free port, replacing
    # ollama_url at startup. Turn off to use the Ollama server at ollama_url instead.
    llm_auto_setup: bool = True
    ollama_version: str = "v0.40.13"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "hf.co/huihui-ai/Huihui-Qwen3.8-27B-abliterated-GGUF"
    ollama_timeout_seconds: float = 1800
    ollama_num_ctx: int = 16384

    hibp_api_key: str = ""
    hibp_base_url: str = "https://haveibeenpwned.com/api/v3"
    hibp_user_agent: str = "PersonalSecurityInfrastructureModeler"


settings = Settings()
