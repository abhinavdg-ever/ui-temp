from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]  # repo root (…/advantmed-imaging-ui)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_mode: Literal["local", "postgres"] = "local"
    data_root: str = "./data/folders"
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/advantmed_imaging"
    api_host: str = "127.0.0.1"
    api_port: int = 8002
    allowed_origins: str = "http://127.0.0.1:5174,http://localhost:5174"

    # File Viewer — Azure Blob (or compatible) source
    file_viewer_blob_enabled: bool = False
    blob_account_url: str = ""
    blob_container: str = ""
    # Path inside container. Tokens: {folder} {filename} {page}
    blob_path_template: str = "{folder}/pages/{filename}"
    # Optional server-side SAS. If empty, UI asks once per session.
    blob_sas_token: str = ""

    @property
    def resolved_data_root(self) -> Path:
        path = Path(self.data_root)
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()
        return path

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def blob_auth_required(self) -> bool:
        """True when Blob mode is on but no SAS is configured server-side."""
        return bool(self.file_viewer_blob_enabled) and not bool(self.blob_sas_token.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
