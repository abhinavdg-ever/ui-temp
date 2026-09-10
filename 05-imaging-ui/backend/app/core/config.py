from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]  # 05-imaging-ui app root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_mode: Literal["local", "postgres"] = "local"
    data_root: str = "./data/folders"
    # Local mode: stacked metadata_R{n}_B{n}.csv for Manifest Details
    # Monorepo: ../06-postgres-db/manifest  |  Nested: ./postgres-db/manifest
    metadata_root: str = "../06-postgres-db/manifest"
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/advantmed_imaging"
    api_host: str = "127.0.0.1"
    api_port: int = 8002
    allowed_origins: str = "http://127.0.0.1:5174,http://localhost:5174"

    # File Viewer — Azure Blob
    file_viewer_blob_enabled: bool = False
    # entra = Microsoft Entra ID (recommended when Shared Key is disabled)
    # sas   = legacy Shared Key / account-or-service SAS (blocked if AllowSharedKeyAccess=false)
    blob_auth_mode: Literal["entra", "sas"] = "entra"
    blob_account_url: str = ""
    blob_container: str = ""
    # Path inside container. Tokens: {folder} {filename} {page}
    blob_path_template: str = "{folder}/pages/{filename}"

    # Entra app registration (optional if using Managed Identity / az login)
    azure_tenant_id: str = ""
    azure_client_id: str = ""
    azure_client_secret: str = ""

    # Legacy SAS only (blob_auth_mode=sas). Not usable when Shared Key is disabled.
    blob_sas_token: str = ""

    @property
    def resolved_data_root(self) -> Path:
        path = Path(self.data_root)
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()
        return path

    @property
    def resolved_metadata_root(self) -> Path:
        """Local-mode CSV root: prefer 06-postgres-db/manifest (legacy: metadata/)."""
        path = Path(self.metadata_root)
        if not path.is_absolute():
            path = (ROOT_DIR / path).resolve()

        candidates: list[Path] = []
        # If .env still says .../metadata, try sibling manifest first
        if path.name.lower() == "metadata":
            candidates.append(path.parent / "manifest")
        candidates.append(path)
        if path.name.lower() == "manifest":
            candidates.append(path.parent / "metadata")
        candidates.extend(
            [
                ROOT_DIR / "postgres-db" / "manifest",
                ROOT_DIR.parent / "06-postgres-db" / "manifest",
                ROOT_DIR / "postgres-db" / "metadata",
                ROOT_DIR.parent / "06-postgres-db" / "metadata",
            ]
        )

        seen: set[Path] = set()
        with_csv: list[Path] = []
        empty_dirs: list[Path] = []
        for cand in candidates:
            resolved = cand.resolve()
            if resolved in seen or not resolved.is_dir():
                continue
            seen.add(resolved)
            has_csv = any(
                p.is_file()
                and p.name.lower().startswith("metadata_r")
                and p.name.lower().endswith(".csv")
                for p in resolved.iterdir()
            )
            if has_csv:
                with_csv.append(resolved)
            else:
                empty_dirs.append(resolved)
        if with_csv:
            return with_csv[0]
        if empty_dirs:
            return empty_dirs[0]
        return path

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def blob_entra_ready(self) -> bool:
        return bool(
            self.file_viewer_blob_enabled
            and self.blob_auth_mode == "entra"
            and self.blob_account_url.strip()
            and self.blob_container.strip()
        )

    @property
    def blob_auth_required(self) -> bool:
        """True only for legacy SAS mode when no server SAS is configured."""
        return (
            bool(self.file_viewer_blob_enabled)
            and self.blob_auth_mode == "sas"
            and not bool(self.blob_sas_token.strip())
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
