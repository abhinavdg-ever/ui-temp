from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.adapters.base import FolderRepository
from app.core.schemas import (
    FolderDetail,
    FolderSummary,
    ImagingDocumentResponse,
    ImagingManifestDetails,
    ImagingPageResult,
    OcrKind,
    OcrRunStatus,
    OcrTextResponse,
    PageSummary,
)
from app.services.metadata_csv import manifest_for_record

PAGE_RE = re.compile(r"^page_(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PLAIN_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)

# API kind → filename suffix: <folder>_<suffix>.{txt|json}
KIND_TO_SUFFIX: dict[str, str] = {
    "preliminary": "prelim",
    "final1": "final1",
    "final2": "final2",
}

OCR_KINDS: tuple[str, ...] = ("preliminary", "final1", "final2")
# final2 (AzDocInt) is JSON; others are plain text
KIND_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "preliminary": (".txt",),
    "final1": (".txt",),
    "final2": (".json", ".txt"),
}


def _page_num_from_name(name: str) -> int | None:
    match = PAGE_RE.match(name) or PLAIN_NUM_RE.match(name)
    if not match:
        return None
    return int(match.group(1))


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def _latest_mtime(paths: list[Path]) -> datetime | None:
    times = [t for p in paths if (t := _mtime(p)) is not None]
    return max(times) if times else None


def _normalize_kind(kind: str) -> OcrKind:
    if kind not in KIND_TO_SUFFIX:
        raise HTTPException(
            status_code=400,
            detail="kind must be preliminary, final1, or final2",
        )
    return kind  # type: ignore[return-value]


def _page_content_from_azdoc(page: dict[str, Any]) -> str:
    content = page.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    lines = page.get("lines")
    if isinstance(lines, list):
        parts = [
            str(line.get("content", "")).strip()
            for line in lines
            if isinstance(line, dict) and line.get("content")
        ]
        if parts:
            return "\n".join(parts)
    return ""


def azdoc_json_to_ocr_text(data: Any) -> str:
    """Convert AzDocInt JSON into marker-separated OCR text for the UI.

    Expected shape (per document):
      { "pages": [ { "fileName": "1.jpg", "content": "...", "lines": [...] }, ... ] }
    """
    if isinstance(data, list):
        pages = data
    elif isinstance(data, dict):
        pages = data.get("pages") or []
    else:
        return ""

    if not isinstance(pages, list):
        return ""

    chunks: list[str] = []
    for idx, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        filename = (
            page.get("fileName")
            or page.get("filename")
            or page.get("file_name")
            or f"{page.get('pageNumber') or idx}.jpg"
        )
        body = _page_content_from_azdoc(page)
        chunks.append(f"===== {filename} =====\n{body}".rstrip())
    if not chunks:
        return ""
    return "\n\n".join(chunks) + "\n"


class LocalFolderRepository(FolderRepository):
    """Reads document folders from a local filesystem tree.

    Layout per folder:
      pages/1.jpg …
      ocr/<folder_name>_prelim.txt    # Preliminary (Tess)
      ocr/<folder_name>_final1.txt    # Final (OSS)
      ocr/<folder_name>_final2.json   # Final (AzDocInt) — JSON with pages[].content
      # text OCR sections: ===== 1.jpg =====

    Manifest Details (DATA_MODE=local): stacked metadata_R{n}_B{n}.csv under metadata_root
    (default 06-postgres-db/manifest). Postgres mode reads manifest_member_list from DB instead.
    """

    def __init__(self, data_root: Path, metadata_root: Path | None = None):
        self.data_root = data_root
        self.metadata_root = metadata_root

    def _folder_dir(self, folder_id: str) -> Path:
        if "/" in folder_id or "\\" in folder_id or folder_id in (".", ".."):
            raise HTTPException(status_code=400, detail="Invalid folder id")
        path = (self.data_root / folder_id).resolve()
        if not str(path).startswith(str(self.data_root.resolve())):
            raise HTTPException(status_code=400, detail="Invalid folder id")
        if not path.is_dir():
            raise HTTPException(status_code=404, detail=f"Folder not found: {folder_id}")
        return path

    def _ocr_path(self, folder_dir: Path, kind: str) -> Path:
        suffix = KIND_TO_SUFFIX.get(kind)
        if not suffix:
            raise HTTPException(
                status_code=400,
                detail="kind must be preliminary, final1, or final2",
            )
        ocr_dir = folder_dir / "ocr"
        for ext in KIND_EXTENSIONS.get(kind, (".txt",)):
            path = ocr_dir / f"{folder_dir.name}_{suffix}{ext}"
            if path.is_file():
                return path
        preferred_ext = KIND_EXTENSIONS.get(kind, (".txt",))[0]
        return ocr_dir / f"{folder_dir.name}_{suffix}{preferred_ext}"

    def _has_ocr(self, folder_dir: Path, kind: str) -> bool:
        path = self._ocr_path(folder_dir, kind)
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _imaging_path(self, folder_dir: Path) -> Path:
        return folder_dir / "imaging" / f"{folder_dir.name}_imaging.json"

    def _has_imaging(self, folder_dir: Path) -> bool:
        path = self._imaging_path(folder_dir)
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _imaging_processed_count(self, folder_dir: Path, page_count: int) -> int:
        """Until Postgres is wired, imaging is always available as dummy when pages exist."""
        if page_count == 0:
            return 0
        return page_count

    def _dummy_manifest(self) -> ImagingManifestDetails:
        return ImagingManifestDetails(
            member=None,
            dob=None,
            memberId=None,
        )

    def _manifest_for_folder(self, folder_id: str) -> ImagingManifestDetails:
        """DATA_MODE=local: read from 06-postgres-db/manifest metadata_Rn_Bn CSVs."""
        if self.metadata_root is not None:
            found = manifest_for_record(self.metadata_root, folder_id)
            if found is not None:
                return found
        return self._dummy_manifest()

    def _dummy_imaging_pages(self, folder_dir: Path, pages: list[tuple[int, Path]]) -> list[ImagingPageResult]:
        """Backup/dummy imaging rows until Postgres schema is wired."""
        manifest = self._manifest_for_folder(folder_dir.name)
        results: list[ImagingPageResult] = []
        for idx, (num, path) in enumerate(pages):
            results.append(
                ImagingPageResult(
                    pageNumber=num,
                    fileName=path.name,
                    memberName=manifest.member if idx == 0 else (manifest.member or f"Member {num}"),
                    memberDob=manifest.dob,
                    memberId=manifest.memberId,
                    memberConfidence=round(0.92 - (idx * 0.02), 2),
                    handwrittenOrPrinted="Printed" if idx % 2 == 0 else "Handwritten",
                    orientationAngle=round(0.5 + idx * 0.15, 2),
                    tiltAngle=round(0.8 + idx * 0.1, 2),
                    mirrored=False,
                    pageQualityConfidence=round(0.94 - idx * 0.02, 2),
                    dos="01/03/2024" if idx % 2 == 0 else "01/04/2024",
                    dosConfidence=round(0.9 - idx * 0.03, 2),
                    pageType="Daily Note" if idx % 2 == 0 else "Progress Note",
                    pageTypeConfidence=round(0.88 - idx * 0.02, 2),
                )
            )
        return results

    def _parse_imaging_manifest(self, data: Any, folder_id: str) -> ImagingManifestDetails:
        # Prefer CSV metadata (local mode); fall back to JSON embedded manifest, then empty
        from_csv = self._manifest_for_folder(folder_id)
        if from_csv.member or from_csv.dob or from_csv.memberId:
            return from_csv
        if isinstance(data, dict):
            raw = data.get("manifest")
            if isinstance(raw, dict):
                try:
                    return ImagingManifestDetails.model_validate(raw)
                except Exception:
                    pass
        return from_csv

    def _parse_imaging_pages(self, data: Any, folder_dir: Path) -> list[ImagingPageResult]:
        raw_pages = data.get("pages") if isinstance(data, dict) else data
        if not isinstance(raw_pages, list):
            return []
        parsed: list[ImagingPageResult] = []
        for item in raw_pages:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(ImagingPageResult.model_validate(item))
            except Exception:
                continue
        if parsed:
            return parsed
        return self._dummy_imaging_pages(folder_dir, self._page_files(folder_dir))

    def _page_files(self, folder_dir: Path) -> list[tuple[int, Path]]:
        """Collect page images from pages/ (preferred) or folder root as fallback.

        Folders that have images but no OCR yet often keep files at the folder root
        until organize_pages.py moves them into pages/.
        """
        candidates: list[Path] = []
        pages_dir = folder_dir / "pages"
        if pages_dir.is_dir():
            candidates.extend(
                entry
                for entry in pages_dir.iterdir()
                if entry.is_file() and not entry.name.startswith("._") and IMAGE_RE.search(entry.name)
            )

        if not candidates:
            skip_names = {"ocr", "pages"}
            for entry in folder_dir.iterdir():
                if not entry.is_file() or entry.name.startswith("._"):
                    continue
                if entry.name.lower() in skip_names:
                    continue
                if IMAGE_RE.search(entry.name):
                    candidates.append(entry)

        numbered: list[tuple[int, Path]] = []
        other: list[Path] = []
        for entry in candidates:
            num = _page_num_from_name(entry.name)
            if num is not None:
                numbered.append((num, entry))
            else:
                other.append(entry)
        numbered.sort(key=lambda x: x[0])
        next_num = (numbered[-1][0] + 1) if numbered else 1
        other.sort(key=lambda p: p.name.lower())
        for path in other:
            numbered.append((next_num, path))
            next_num += 1
        return numbered

    def _ocr_processed_count(self, folder_dir: Path, page_count: int) -> int:
        """Count pages as OCR-processed only when at least one OCR artifact exists."""
        if page_count == 0:
            return 0
        if any(self._has_ocr(folder_dir, kind) for kind in OCR_KINDS):
            return page_count
        return 0

    def _ocr_status(self, folder_dir: Path) -> OcrRunStatus:
        """Derive status from available OCR artifacts.

        All three outputs (prelim, final1, final2) → COMPLETED ("OCR Completed").
        Any partial OCR → IN_PROGRESS; none → QUEUED.
        """
        present = sum(1 for kind in OCR_KINDS if self._has_ocr(folder_dir, kind))
        if present == len(OCR_KINDS):
            return "COMPLETED"
        if present > 0:
            return "IN_PROGRESS"
        return "QUEUED"

    def _touch_paths(self, folder_dir: Path, pages: list[tuple[int, Path]]) -> list[Path]:
        paths = [folder_dir, *(p for _, p in pages)]
        for kind in OCR_KINDS:
            ocr = self._ocr_path(folder_dir, kind)
            if ocr.is_file():
                paths.append(ocr)
        imaging = self._imaging_path(folder_dir)
        if imaging.is_file():
            paths.append(imaging)
        status_file = folder_dir / "ocr" / "ocr_run_status.txt"
        if status_file.is_file():
            paths.append(status_file)
        return paths

    def list_folders(self) -> list[FolderSummary]:
        if not self.data_root.is_dir():
            return []

        summaries: list[FolderSummary] = []
        for entry in sorted(self.data_root.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            pages = self._page_files(entry)
            page_count = len(pages)
            summaries.append(
                FolderSummary(
                    id=entry.name,
                    name=entry.name,
                    page_count=page_count,
                    ocr_processed=self._ocr_processed_count(entry, page_count),
                    imaging_processed=self._imaging_processed_count(entry, page_count),
                    ocr_status=self._ocr_status(entry),
                    last_updated_at=_latest_mtime(self._touch_paths(entry, pages)),
                )
            )
        summaries.sort(
            key=lambda f: f.last_updated_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return summaries

    def get_folder(self, folder_id: str) -> FolderDetail:
        folder_dir = self._folder_dir(folder_id)
        pages = self._page_files(folder_dir)
        has_prelim = self._has_ocr(folder_dir, "preliminary")
        has_final1 = self._has_ocr(folder_dir, "final1")
        has_final2 = self._has_ocr(folder_dir, "final2")
        has_imaging = True  # dummy imaging always available pre-Postgres
        page_summaries = [
            PageSummary(
                page_number=num,
                filename=path.name,
                image_url=f"/api/folders/{folder_id}/pages/{num}/image",
                has_preliminary_ocr=has_prelim,
                has_final1_ocr=has_final1,
                has_final2_ocr=has_final2,
                has_imaging=has_imaging and len(pages) > 0,
            )
            for num, path in pages
        ]
        return FolderDetail(
            id=folder_id,
            name=folder_dir.name,
            page_count=len(pages),
            ocr_processed=self._ocr_processed_count(folder_dir, len(pages)),
            imaging_processed=self._imaging_processed_count(folder_dir, len(pages)),
            ocr_status=self._ocr_status(folder_dir),
            last_updated_at=_latest_mtime(self._touch_paths(folder_dir, pages)),
            pages=page_summaries,
        )

    def get_page_image_path(self, folder_id: str, page_number: int) -> Path:
        folder_dir = self._folder_dir(folder_id)
        for num, path in self._page_files(folder_dir):
            if num == page_number:
                return path
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found in {folder_id}")

    def get_ocr_text(self, folder_id: str, kind: str) -> OcrTextResponse:
        normalized = _normalize_kind(kind)
        folder_dir = self._folder_dir(folder_id)
        path = self._ocr_path(folder_dir, normalized)
        if not path.is_file():
            expected = f"{folder_dir.name}_{KIND_TO_SUFFIX[normalized]}"
            raise HTTPException(
                status_code=404,
                detail=f"No {normalized} OCR file ({expected}.json/.txt) in {folder_id}",
            )

        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid AzDocInt JSON in {path.name}: {exc}",
                ) from exc
            text = azdoc_json_to_ocr_text(data)
        else:
            text = raw

        return OcrTextResponse(folder_id=folder_id, kind=normalized, text=text)

    def get_imaging(self, folder_id: str) -> ImagingDocumentResponse:
        """Load imaging JSON, or synthesize dummy page rows if missing (pre-Postgres)."""
        folder_dir = self._folder_dir(folder_id)
        pages = self._page_files(folder_dir)
        path = self._imaging_path(folder_dir)

        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid imaging JSON in {path.name}: {exc}",
                ) from exc
            return ImagingDocumentResponse(
                folder_id=folder_id,
                manifest=self._parse_imaging_manifest(data, folder_id),
                pages=self._parse_imaging_pages(data, folder_dir),
            )

        # Backup: always return dummy values so Imaging UI works before Postgres
        return ImagingDocumentResponse(
            folder_id=folder_id,
            manifest=self._manifest_for_folder(folder_id),
            pages=self._dummy_imaging_pages(folder_dir, pages),
        )
