# Configuration and environment management

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


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
    
    # Database/Vector Store Settings
    chromadb_host: str = Field(default="localhost", env="CHROMADB_HOST")
    chromadb_port: int = Field(default=8002, env="CHROMADB_PORT")
    chromadb_collection_name: str = Field(default="legal_documents", env="CHROMADB_COLLECTION")
    
    # Model Settings
    model_endpoint: str = Field(default="http://localhost:8001", env="MODEL_ENDPOINT")
    model_name: str = Field(default="meta-llama/Llama-2-70b-chat-hf", env="MODEL_NAME")
    max_tokens: int = Field(default=2048, env="MAX_TOKENS")
    temperature: float = Field(default=0.1, env="TEMPERATURE")
    
    # Embedding Settings
    embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", env="EMBEDDING_MODEL")
    embedding_dimension: int = Field(default=384, env="EMBEDDING_DIMENSION")
    
    # Document Processing
    max_file_size_mb: int = Field(default=50, env="MAX_FILE_SIZE_MB")
    supported_file_types: list = Field(default=[".pdf", ".txt", ".docx"], env="SUPPORTED_FILE_TYPES")
    chunk_size: int = Field(default=1000, env="CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, env="CHUNK_OVERLAP")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/app.log", env="LOG_FILE")
    
    # Security & Audit
    enable_audit_logging: bool = Field(default=True, env="ENABLE_AUDIT_LOGGING")
    allowed_ips: Optional[str] = Field(default=None, env="ALLOWED_IPS")  # Comma-separated IPs
    
    # n8n Integration
    n8n_webhook_url: Optional[str] = Field(default=None, env="N8N_WEBHOOK_URL")
    slack_webhook_url: Optional[str] = Field(default=None, env="SLACK_WEBHOOK_URL")
    
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
            return [ip.strip() for ip in self.allowed_ips.split(",")]
        return []


# Global settings instance
settings = Settings()

# Create logs directory if it doesn't exist
os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)
