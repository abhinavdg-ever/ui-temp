from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

OcrKind = Literal["preliminary", "final1", "final2"]
OcrRunStatus = Literal["QUEUED", "IN_PROGRESS", "COMPLETED", "FAILED"]
BlobAuthMode = Literal["entra", "sas"]


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
    has_imaging: bool = False


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


class ImagingPageResult(BaseModel):
    """Per-page imaging fields (dummy/local JSON for now; Postgres later)."""

    pageNumber: int
    fileName: str
    memberName: str | None = None
    memberDob: str | None = None
    memberId: str | None = None
    memberConfidence: float | None = None
    handwrittenOrPrinted: str | None = None
    orientationAngle: float | None = None
    tiltAngle: float | None = None
    mirrored: bool | None = None
    pageQualityConfidence: float | None = None
    dos: str | None = None
    dosConfidence: float | None = None
    pageType: str | None = None
    pageTypeConfidence: float | None = None


class ImagingManifestDetails(BaseModel):
    """Expected manifest identity for the chart.

    DATA_MODE=local → postgres-db/manifest/metadata_R*_B*.csv
    DATA_MODE=postgres → manifest_member_list
    """

    member: str | None = None
    dob: str | None = None
    memberId: str | None = None


class ImagingDocumentResponse(BaseModel):
    folder_id: str
    manifest: ImagingManifestDetails = Field(default_factory=ImagingManifestDetails)
    pages: list[ImagingPageResult] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    data_mode: str


class AppConfigResponse(BaseModel):
    data_mode: str
    file_viewer_blob_enabled: bool = False
    blob_auth_mode: BlobAuthMode = "entra"
    blob_account_url: str = ""
    blob_container: str = ""
    blob_path_template: str = "{folder}/pages/{filename}"
    blob_entra_ready: bool = False
    blob_auth_required: bool = False
    blob_sas_configured: bool = False
