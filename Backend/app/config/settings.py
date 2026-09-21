from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    DATABASE_URL: str
    SECRET_KEY: str
    GEMINI_API_KEY: str

    FRONTEND_URL: str = "http://localhost:5173"

    CHROMA_DB_PATH: str = "chroma_db"
    REPOSITORIES_PATH: str = "repositories"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


settings = Settings()