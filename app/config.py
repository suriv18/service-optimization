from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    osrm_url: str = "http://localhost:5000"
    log_level: str = "INFO"

    model_config = {"env_file": ".env"}


settings = Settings()
