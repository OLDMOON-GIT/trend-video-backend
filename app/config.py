"""Application configuration."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings."""

    # API Configuration
    api_title: str = "Trend Video Backend API"
    api_version: str = "1.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database
    database_url: str = "sqlite:///./trend_video.db"

    # Storage
    storage_path: str = "./storage"
    output_path: str = "./output"
    temp_path: str = "./temp"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # OpenAI
    openai_api_key: str = ""

    # Groq (무료 대안)
    groq_api_key: str = ""

    # Replicate
    replicate_api_token: str = ""

    # Hugging Face
    huggingface_api_key: str = ""

    # Google APIs
    google_api_key: str = ""
    google_search_engine_id: str = ""

    # LLM Configuration
    llm_provider: str = "groq"  # openai, groq, ollama
    llm_model: str = "llama-3.3-70b-versatile"

    # Image Generation
    image_provider: str = "replicate"  # openai, replicate, huggingface, google

    # TTS Configuration
    tts_voice: str = "ko-KR-SunHiNeural"

    # Whisper Configuration
    whisper_model: str = "base"  # tiny, base, small, medium, large

    # JWT
    jwt_secret_key: str = "your-secret-key-change-this"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
