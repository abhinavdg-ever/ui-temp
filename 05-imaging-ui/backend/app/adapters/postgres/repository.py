"""Postgres-backed folder repository (DATA_MODE=postgres).

- Manifest Details ← manifest_member_list
- OCR text ← ocr_results (tesseract / docling / azuredocintel)
- Pages / images still use DATA_ROOT until fully DB-backed
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.adapters.base import FolderRepository
from app.adapters.local.repository import LocalFolderRepository, _normalize_kind
from app.core.schemas import (
    FolderDetail,
    FolderSummary,
    ImagingDocumentResponse,
    ImagingManifestDetails,
    OcrTextResponse,
    PageSummary,
)

# API kind → ocr_results.ocr_type
KIND_TO_OCR_TYPE: dict[str, str] = {
    "preliminary": "tesseract",
    "final1": "docling",
    "final2": "azuredocintel",
}


def _psycopg_url(database_url: str) -> str:
    """Accept sqlalchemy-style postgresql+psycopg:// and plain postgresql://."""
    url = database_url.strip()
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgres+psycopg://"):
        return "postgresql://" + url[len("postgres+psycopg://") :]
    return url


class PostgresFolderRepository(FolderRepository):
    def __init__(self, database_url: str, data_root: Path | None = None):
        self.database_url = _psycopg_url(database_url)
        self._local = LocalFolderRepository(data_root) if data_root is not None else None

    def _require_local(self) -> LocalFolderRepository:
        if self._local is None:
            raise HTTPException(
                status_code=501,
                detail="Postgres mode needs DATA_ROOT for page images until fully DB-backed.",
            )
        return self._local

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise HTTPException(
                status_code=501,
                detail="Install psycopg: pip install 'psycopg[binary]'",
            ) from exc
        return psycopg.connect(self.database_url)

    def list_folders(self) -> list[FolderSummary]:
        return self._require_local().list_folders()

    def get_folder(self, folder_id: str) -> FolderDetail:
        """Page images from local; OCR presence flags from ocr_results when available."""
        detail = self._require_local().get_folder(folder_id)
        flags = self._ocr_flags_from_db(folder_id)
        if flags is None:
            return detail

        pages: list[PageSummary] = []
        for p in detail.pages:
            page_flags = flags.get(p.filename, {})
            pages.append(
                PageSummary(
                    page_number=p.page_number,
                    filename=p.filename,
                    image_url=p.image_url,
                    has_preliminary_ocr=bool(page_flags.get("tesseract")),
                    has_final1_ocr=bool(page_flags.get("docling")),
                    has_final2_ocr=bool(page_flags.get("azuredocintel")),
                    has_imaging=p.has_imaging,
                )
            )

        kinds_present = {
            k
            for page_flags in flags.values()
            for k, ok in page_flags.items()
            if ok
        }
        ocr_processed = sum(
            1
            for k in ("tesseract", "docling", "azuredocintel")
            if k in kinds_present
        )
        if ocr_processed == 3:
            ocr_status = "COMPLETED"
        elif ocr_processed > 0:
            ocr_status = "IN_PROGRESS"
        else:
            ocr_status = detail.ocr_status

        return FolderDetail(
            id=detail.id,
            name=detail.name,
            page_count=detail.page_count,
            ocr_processed=ocr_processed,
            imaging_processed=detail.imaging_processed,
            ocr_status=ocr_status,  # type: ignore[arg-type]
            last_updated_at=detail.last_updated_at,
            pages=pages,
        )

    def get_page_image_path(self, folder_id: str, page_number: int) -> Path:
        return self._require_local().get_page_image_path(folder_id, page_number)

    def _ocr_flags_from_db(self, folder_id: str) -> dict[str, dict[str, bool]] | None:
        """page_name → {ocr_type: True}."""
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT p.page_name, o.ocr_type
                        FROM ocr_results o
                        JOIN chart_list c ON c.id = o.chart_id
                        JOIN page_list p ON p.id = o.page_id
                        WHERE c.chart_name = %s
                          AND o.raw_text IS NOT NULL
                          AND length(trim(o.raw_text)) > 0
                        """,
                        (folder_id,),
                    )
                    rows = cur.fetchall()
        except Exception:
            return None

        out: dict[str, dict[str, bool]] = {}
        for page_name, ocr_type in rows:
            out.setdefault(page_name, {})[ocr_type] = True
        return out

    def get_ocr_text(self, folder_id: str, kind: str) -> OcrTextResponse:
        """Assemble OCR from ocr_results into ===== page ===== marker text for the UI."""
        normalized = _normalize_kind(kind)
        ocr_type = KIND_TO_OCR_TYPE[normalized]

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT p.page_name, o.raw_text
                        FROM ocr_results o
                        JOIN chart_list c ON c.id = o.chart_id
                        JOIN page_list p ON p.id = o.page_id
                        WHERE c.chart_name = %s
                          AND o.ocr_type = %s
                        ORDER BY p.id
                        """,
                        (folder_id, ocr_type),
                    )
                    rows = cur.fetchall()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Postgres OCR lookup failed: {exc}",
            ) from exc

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No ocr_results for chart={folder_id!r} ocr_type={ocr_type!r}",
            )

        chunks: list[str] = []
        for page_name, raw_text in rows:
            body = (raw_text or "").strip()
            # If a full AzDocInt JSON blob was stored, leave it; UI page splitter
            # still works when we wrap per page_name.
            chunks.append(f"===== {page_name} =====\n{body}".rstrip())

        return OcrTextResponse(
            folder_id=folder_id,
            kind=normalized,
            text="\n\n".join(chunks),
        )

    def _manifest_from_db(self, folder_id: str) -> ImagingManifestDetails | None:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT m.member_name, m.member_dob, m.external_member_id
                        FROM manifest_member_list m
                        JOIN chart_list c ON c.id = m.chart_id
                        WHERE c.chart_name = %s
                        ORDER BY m.id
                        LIMIT 1
                        """,
                        (folder_id,),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Postgres manifest lookup failed: {exc}",
            ) from exc

        if not row:
            return None
        name, dob, member_id = row
        return ImagingManifestDetails(
            member=name,
            dob=dob.strftime("%m/%d/%Y") if dob is not None else None,
            memberId=member_id,
        )

    def get_imaging(self, folder_id: str) -> ImagingDocumentResponse:
        """Pages from local imaging JSON/dummy; manifest from Postgres."""
        local = self._require_local()
        doc = local.get_imaging(folder_id)
        db_manifest = self._manifest_from_db(folder_id)
        if db_manifest is not None:
            return ImagingDocumentResponse(
                folder_id=doc.folder_id,
                manifest=db_manifest,
                pages=doc.pages,
            )
        return doc
