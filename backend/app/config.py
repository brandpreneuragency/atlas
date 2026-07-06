from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_")

    data_dir: Path = Path("/data")
    atlas_root: Path = Path("/opt/atlas")
    hermes_runs_url: str = "http://hermes:8642"
    hermes_admin_url: str = "http://hermes:9119"
    hermes_api_key: str = ""
    password: str = ""
    secret_key: str = ""
    tz: str = "Europe/Istanbul"
    port: int = 8700
    static_dir: Path | None = Path("/app/static")
    mock_hermes: bool = False
    dev_mode: bool = False
    public_url: str = "https://atlas.brandpreneur.net"


def get_settings() -> Settings:
    return Settings()
