# Configuration and environment management

import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

KNOWN_PLACEHOLDER_SECRETS = {
    "your-secret-key-here-change-this-in-production",
    "your-secret-key",
    "changeme",
    "change-me",
    "secret",
}


class Settings(BaseSettings):
    """Application configuration with environment variable support."""
    
    # Application Settings
    app_name: str = "Local Legal AI"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, env="DEBUG")
    
    # Server Settings
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    
    # Security Settings
    secret_key: str = Field(env="SECRET_KEY", description="JWT secret key")
    algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=1440, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 24 hours

    # Sign-in throttling: failures per (username, client address) within the window
    login_max_failures: int = Field(default=5, env="LOGIN_MAX_FAILURES")
    login_lockout_minutes: int = Field(default=15, env="LOGIN_LOCKOUT_MINUTES")

    @field_validator("secret_key")
    @classmethod
    def _reject_weak_secret(cls, value: str) -> str:
        # Anyone who knows a published placeholder could forge sign-in tokens.
        if value.strip() in KNOWN_PLACEHOLDER_SECRETS or len(value.strip()) < 16:
            raise ValueError(
                "SECRET_KEY is missing, a published placeholder, or shorter than 16 characters. "
                "Set a long random value in .env, e.g. "
                "python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return value
    
    # Local testing environment (scripts/demo.py) only. Relaxes the password rules
    # so the demo can sign in as admin / admin: it holds nothing but fictional
    # sample agreements and listens on localhost alone. Refused on any other
    # address, so it cannot weaken a networked install by accident.
    demo_mode: bool = Field(default=False, env="DEMO_MODE")

    @field_validator("demo_mode")
    @classmethod
    def _demo_mode_only_on_loopback(cls, value: bool, info) -> bool:
        host = (info.data.get("host") or "").strip()
        if value and host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                f"DEMO_MODE relaxes the password rules and is only allowed when HOST is "
                f"127.0.0.1 or localhost (got {host!r}). Unset DEMO_MODE for a real install."
            )
        return value

    # Database/Vector Store Settings
    chromadb_host: str = Field(default="localhost", env="CHROMADB_HOST")
    chromadb_port: int = Field(default=8002, env="CHROMADB_PORT")
    chromadb_collection_name: str = Field(default="legal_documents", env="CHROMADB_COLLECTION")
    
    # Model Settings — any OpenAI-compatible server: vLLM (model/vllm_launcher.sh,
    # port 8001), Ollama (http://localhost:11434), llama.cpp server, LM Studio.
    llm_enabled: bool = Field(default=True, env="LLM_ENABLED")
    model_endpoint: str = Field(default="http://localhost:8001", env="MODEL_ENDPOINT")
    model_name: str = Field(default="legal-ai-model", env="MODEL_NAME")
    llm_timeout_seconds: float = Field(default=120.0, env="LLM_TIMEOUT_SECONDS")
    max_tokens: int = Field(default=2048, env="MAX_TOKENS")
    temperature: float = Field(default=0.1, env="TEMPERATURE")
    
    # Embedding Settings
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=384, env="EMBEDDING_DIMENSION")
    
    # Document Processing
    max_file_size_mb: int = Field(default=50, env="MAX_FILE_SIZE_MB")
    supported_file_types: list = Field(default=[".pdf", ".txt", ".docx"], env="SUPPORTED_FILE_TYPES")
    # Chunk sizes are in words; ~220 words fits the 256-token window of MiniLM.
    chunk_size: int = Field(default=220, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=40, env="CHUNK_OVERLAP")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", env="LOG_FILE")
    
    # Security & Audit
    enable_audit_logging: bool = Field(default=True, env="ENABLE_AUDIT_LOGGING")
    allowed_ips: Optional[str] = Field(default=None, env="ALLOWED_IPS")  # Comma-separated IPs or CIDRs
    cors_origins: str = Field(default="http://localhost:8501,http://127.0.0.1:8501", env="CORS_ORIGINS")
    
    # Automation & notifications (n8n, Slack)
    n8n_webhook_url: Optional[str] = Field(default=None, env="N8N_WEBHOOK_URL")
    slack_webhook_url: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    webhook_secret: Optional[str] = Field(default=None, env="WEBHOOK_SECRET")
    notify_events: str = Field(default="", env="NOTIFY_EVENTS")  # comma-separated; empty = all

    # Watched-folder ingestion
    inbox_enabled: bool = Field(default=True, env="INBOX_ENABLED")
    inbox_dir: str = Field(default="data/inbox", env="INBOX_DIR")
    inbox_poll_seconds: float = Field(default=10.0, env="INBOX_POLL_SECONDS")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }

    def get_chromadb_url(self) -> str:
        """Get the complete ChromaDB URL."""
        return f"http://{self.chromadb_host}:{self.chromadb_port}"
    
    def get_allowed_ips_list(self) -> list:
        """Parse comma-separated allowed IPs into a list."""
        if self.allowed_ips:
            return [ip.strip() for ip in self.allowed_ips.split(",") if ip.strip()]
        return []

    def get_cors_origins_list(self) -> list:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


# Global settings instance
settings = Settings()

# Create logs directory if it doesn't exist
os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
