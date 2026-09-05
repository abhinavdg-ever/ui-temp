from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FolderSummary(BaseModel):
    id: str
    name: str
    page_count: int = 0
    ocr_processed: int = 0
    imaging_processed: int = 0
    last_updated_at: datetime | None = None


class PageSummary(BaseModel):
    page_number: int
    filename: str
    image_url: str
    has_preliminary_ocr: bool = False
    has_final_ocr: bool = False


class FolderDetail(BaseModel):
    id: str
    name: str
    page_count: int
    ocr_processed: int
    imaging_processed: int = 0
    last_updated_at: datetime | None = None
    pages: list[PageSummary] = Field(default_factory=list)


class OcrTextResponse(BaseModel):
    folder_id: str
    kind: Literal["preliminary", "final"]
    text: str


class HealthResponse(BaseModel):
    status: str
    data_mode: str
