from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.adapters.base import FolderRepository
from app.adapters.factory import get_repository
from app.core.config import get_settings
from app.core.schemas import FolderDetail, FolderSummary, HealthResponse, OcrTextResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", data_mode=settings.data_mode)


@router.get("/folders", response_model=list[FolderSummary])
def list_folders(repo: FolderRepository = Depends(get_repository)) -> list[FolderSummary]:
    return repo.list_folders()


@router.get("/folders/{folder_id}", response_model=FolderDetail)
def get_folder(folder_id: str, repo: FolderRepository = Depends(get_repository)) -> FolderDetail:
    return repo.get_folder(folder_id)


@router.get("/folders/{folder_id}/pages/{page_number}/image")
def get_page_image(
    folder_id: str,
    page_number: int,
    repo: FolderRepository = Depends(get_repository),
) -> FileResponse:
    path = repo.get_page_image_path(folder_id, page_number)
    return FileResponse(path, media_type=_media_type(path.suffix))


@router.get("/folders/{folder_id}/ocr", response_model=OcrTextResponse)
def get_folder_ocr(
    folder_id: str,
    kind: str = "preliminary",
    repo: FolderRepository = Depends(get_repository),
) -> OcrTextResponse:
    return repo.get_ocr_text(folder_id, kind)


def _media_type(suffix: str) -> str:
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }
    return mapping.get(suffix.lower(), "application/octet-stream")
