from pathlib import Path

from fastapi import HTTPException

from app.adapters.base import FolderRepository
from app.core.schemas import FolderDetail, FolderSummary, OcrTextResponse


class PostgresFolderRepository(FolderRepository):
    """Postgres-backed folder repository.

    Wired for DATA_MODE=postgres but not implemented yet — local mode is the active path.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url

    def list_folders(self) -> list[FolderSummary]:
        raise HTTPException(
            status_code=501,
            detail="Postgres mode is not implemented yet. Set DATA_MODE=local in .env.",
        )

    def get_folder(self, folder_id: str) -> FolderDetail:
        raise HTTPException(
            status_code=501,
            detail="Postgres mode is not implemented yet. Set DATA_MODE=local in .env.",
        )

    def get_page_image_path(self, folder_id: str, page_number: int) -> Path:
        raise HTTPException(
            status_code=501,
            detail="Postgres mode is not implemented yet. Set DATA_MODE=local in .env.",
        )

    def get_ocr_text(self, folder_id: str, kind: str) -> OcrTextResponse:
        raise HTTPException(
            status_code=501,
            detail="Postgres mode is not implemented yet. Set DATA_MODE=local in .env.",
        )
