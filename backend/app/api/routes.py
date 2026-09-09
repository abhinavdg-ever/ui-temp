from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

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
from app.services.blob_store import download_blob_bytes

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
    encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
    sas = settings.blob_sas_token.strip()
    if sas.startswith("?"):
        sas = sas[1:]
    base = f"{account}/{container}/{encoded_key}"
    return f"{base}?{sas}" if sas else base


def _filename_for_page(repo: FolderRepository, folder_id: str, page_number: int) -> str:
    detail = repo.get_folder(folder_id)
    for page in detail.pages:
        if page.page_number == page_number:
            return page.filename
    raise HTTPException(status_code=404, detail=f"Page {page_number} not found in {folder_id}")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", data_mode=settings.data_mode)


@router.get("/config", response_model=AppConfigResponse)
def app_config() -> AppConfigResponse:
    """Public UI config. Does not expose secrets."""
    settings = get_settings()
    sas_configured = bool(settings.blob_sas_token.strip())
    return AppConfigResponse(
        data_mode=settings.data_mode,
        file_viewer_blob_enabled=settings.file_viewer_blob_enabled,
        blob_auth_mode=settings.blob_auth_mode,
        blob_account_url=settings.blob_account_url.strip().rstrip("/"),
        blob_container=settings.blob_container.strip().strip("/"),
        blob_path_template=settings.blob_path_template.strip() or "{folder}/pages/{filename}",
        blob_entra_ready=settings.blob_entra_ready,
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
):
    """Serve a page image from Azure Blob.

    - blob_auth_mode=entra: proxy bytes using Microsoft Entra ID (works with Shared Key disabled)
    - blob_auth_mode=sas: redirect to object URL with server SAS (requires Shared Key allowed)
    """
    settings = get_settings()
    if not settings.file_viewer_blob_enabled:
        raise HTTPException(status_code=400, detail="Blob viewer is disabled")

    filename = _filename_for_page(repo, folder_id, page_number)

    if settings.blob_auth_mode == "entra":
        data, media_type = download_blob_bytes(
            folder_id=folder_id,
            filename=filename,
            page_number=page_number,
        )
        return Response(
            content=data,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=120"},
        )

    if not settings.blob_sas_token.strip():
        raise HTTPException(
            status_code=400,
            detail="Server SAS not configured; set BLOB_SAS_TOKEN or use BLOB_AUTH_MODE=entra",
        )
    url = _build_blob_url(
        settings,
        folder_id=folder_id,
        filename=filename,
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
