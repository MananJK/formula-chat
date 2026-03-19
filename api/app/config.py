from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", alias="OPENAI_MODEL")

    # PostgreSQL
    database_url: str = Field(..., alias="DATABASE_URL")
    database_query_timeout: int = Field(5, alias="DATABASE_QUERY_TIMEOUT")

    # pgvector RAG
    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")
    rag_top_k: int = Field(5, alias="RAG_TOP_K")

    # API
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    api_cors_origins: list[str] = Field(
        default=["http://localhost:5173"],
        alias="API_CORS_ORIGINS",
    )
    rate_limit_per_minute: int = Field(20, alias="RATE_LIMIT_PER_MINUTE")

    # Environment
    env: str = Field("development", alias="ENV")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
