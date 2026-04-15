"""Configuration for the Devin Issue Triage Orchestrator."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Devin API (v3 - Service Users)
    devin_api_key: str = ""
    devin_org_id: str = ""
    devin_api_base_url: str = "https://api.devin.ai/v3"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""
    target_repo: str = "jessie-young/demo-finserv-repo"

    # Polling
    poll_interval_seconds: int = 8
    max_poll_duration_seconds: int = 3600

    # App
    app_title: str = "Devin Issue Triage Orchestrator"
    debug: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
