from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OcrKind = Literal["preliminary", "final1", "final2"]
OcrRunStatus = Literal["QUEUED", "IN_PROGRESS", "COMPLETED", "FAILED"]


class FolderSummary(BaseModel):
    id: str
    name: str
    page_count: int = 0
    ocr_processed: int = 0
    imaging_processed: int = 0
    ocr_status: OcrRunStatus = "QUEUED"
    last_updated_at: datetime | None = None


class PageSummary(BaseModel):
    page_number: int
    filename: str
    image_url: str
    has_preliminary_ocr: bool = False
    has_final1_ocr: bool = False
    has_final2_ocr: bool = False


class FolderDetail(BaseModel):
    id: str
    name: str
    page_count: int
    ocr_processed: int
    imaging_processed: int = 0
    ocr_status: OcrRunStatus = "QUEUED"
    last_updated_at: datetime | None = None
    pages: list[PageSummary] = Field(default_factory=list)


class OcrTextResponse(BaseModel):
    folder_id: str
    kind: OcrKind
    text: str


class HealthResponse(BaseModel):
    status: str
    data_mode: str


class AppConfigResponse(BaseModel):
    data_mode: str
    file_viewer_blob_enabled: bool = False
    blob_account_url: str = ""
    blob_container: str = ""
    blob_path_template: str = "{folder}/pages/{filename}"
    # When true, UI must collect a SAS / access token once for the session
    blob_auth_required: bool = False
    # Present only when configured server-side (not required from UI)
    blob_sas_configured: bool = False
