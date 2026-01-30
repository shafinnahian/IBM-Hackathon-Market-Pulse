from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    cloudant_url: str = ""
    cloudant_apikey: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
