"""
Configuration settings for the Bulk-Scanner API
"""

from typing import List, Optional
from pydantic import BaseSettings, Field
from pydantic_settings import BaseSettings as BaseSettingsV2

class Settings(BaseSettingsV2):
    """Application settings"""
    
    # App Info
    app_name: str = "Bulk-Scanner Résumé Matcher API"
    version: str = "1.0.0"
    debug: bool = Field(default=False, env="DEBUG")
    
    # Database
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/bulk_scanner",
        env="DATABASE_URL"
    )
    
    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        env="REDIS_URL"
    )
    
    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        env="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0",
        env="CELERY_RESULT_BACKEND"
    )
    
    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-3.5-turbo", env="OPENAI_MODEL")
    embedding_model: str = Field(
        default="text-embedding-ada-002",
        env="EMBEDDING_MODEL"
    )
    
    # Security
    secret_key: str = Field(
        default="your-secret-key-change-this-in-production",
        env="SECRET_KEY"
    )
    
    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "chrome-extension://*"],
        env="ALLOWED_ORIGINS"
    )
    
    # Scraping
    max_concurrent_scrapes: int = Field(default=5, env="MAX_CONCURRENT_SCRAPES")
    scrape_timeout: int = Field(default=30, env="SCRAPE_TIMEOUT")
    
    # Matching
    default_match_threshold: float = Field(default=0.7, env="DEFAULT_MATCH_THRESHOLD")
    max_jobs_per_scan: int = Field(default=50, env="MAX_JOBS_PER_SCAN")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings() 