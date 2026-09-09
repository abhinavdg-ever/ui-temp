from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from app.adapters.base import FolderRepository
from app.adapters.factory import get_repository
from app.core.config import Settings, get_settings
from app.core.schemas import (
    AppConfigResponse,
    FolderDetail,
    FolderSummary,
    HealthResponse,
    OcrTextResponse,
)

router = APIRouter()


def _build_blob_url(
    settings: Settings,
    *,
    folder_id: str,
    filename: str,
    page_number: int,
) -> str:
    account = settings.blob_account_url.strip().rstrip("/")
    container = settings.blob_container.strip().strip("/")
    if not account or not container:
        raise HTTPException(status_code=400, detail="BLOB_ACCOUNT_URL / BLOB_CONTAINER not configured")

    template = settings.blob_path_template.strip() or "{folder}/pages/{filename}"
    key = (
        template.replace("{folder}", folder_id)
        .replace("{filename}", filename)
        .replace("{page}", str(page_number))
        .lstrip("/")
    )
    # Encode path segments but keep slashes
    encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
    sas = settings.blob_sas_token.strip()
    if sas.startswith("?"):
        sas = sas[1:]
    base = f"{account}/{container}/{encoded_key}"
    return f"{base}?{sas}" if sas else base


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", data_mode=settings.data_mode)


@router.get("/config", response_model=AppConfigResponse)
def app_config() -> AppConfigResponse:
    """Public UI config. Does not expose the SAS secret itself."""
    settings = get_settings()
    sas_configured = bool(settings.blob_sas_token.strip())
    return AppConfigResponse(
        data_mode=settings.data_mode,
        file_viewer_blob_enabled=settings.file_viewer_blob_enabled,
        blob_account_url=settings.blob_account_url.strip().rstrip("/"),
        blob_container=settings.blob_container.strip().strip("/"),
        blob_path_template=settings.blob_path_template.strip() or "{folder}/pages/{filename}",
        blob_auth_required=settings.blob_auth_required,
        blob_sas_configured=sas_configured,
    )


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


@router.get("/blob/{folder_id}/pages/{page_number}/image")
def get_blob_page_image(
    folder_id: str,
    page_number: int,
    repo: FolderRepository = Depends(get_repository),
) -> RedirectResponse:
    """Redirect to blob object URL using server-side SAS (when configured in .env)."""
    settings = get_settings()
    if not settings.file_viewer_blob_enabled:
        raise HTTPException(status_code=400, detail="Blob viewer is disabled")
    if not settings.blob_sas_token.strip():
        raise HTTPException(
            status_code=400,
            detail="Server SAS not configured; authenticate once in the UI instead",
        )
    path = repo.get_page_image_path(folder_id, page_number)
    url = _build_blob_url(
        settings,
        folder_id=folder_id,
        filename=path.name,
        page_number=page_number,
    )
    return RedirectResponse(url=url, status_code=307)


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
