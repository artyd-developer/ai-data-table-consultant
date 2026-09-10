from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    ollama_base_url: str
    ollama_model: str = "qwen3:8b"

    mariadb_host: str = "mariadb"
    mariadb_port: int = 3306
    mariadb_database: str = "business_agent"
    mariadb_user: str = "app"
    mariadb_password: str = "app"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
