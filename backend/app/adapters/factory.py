from functools import lru_cache

from app.adapters.base import FolderRepository
from app.adapters.local.repository import LocalFolderRepository
from app.adapters.postgres.repository import PostgresFolderRepository
from app.core.config import Settings, get_settings


@lru_cache
def get_repository() -> FolderRepository:
    settings = get_settings()
    return build_repository(settings)


def build_repository(settings: Settings) -> FolderRepository:
    if settings.data_mode == "postgres":
        return PostgresFolderRepository(settings.database_url)
    return LocalFolderRepository(settings.resolved_data_root)
