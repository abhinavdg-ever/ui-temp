from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime, timezone
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


def _fmt_dos_display(raw: str | date | None) -> str | None:
    """Normalize dates to MM/DD/YYYY for the Imaging UI."""
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw.strftime("%m/%d/%Y")
    value = str(raw).strip()
    if not value or value.lower() in {"unknown", "null", "none"}:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
        try:
            return datetime.strptime(value, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return value


def _dos_row_fields(row: dict[str, str]) -> dict[str, str | None]:
    dos_from = _fmt_dos_display(row.get("dos_from_iso") or row.get("dos_from") or row.get("dos"))
    dos_to = _fmt_dos_display(row.get("dos_to_iso") or row.get("dos_to") or "")
    if dos_from and not dos_to and (row.get("dos_from") or row.get("dos_from_iso") or row.get("dos")):
        dos_to = dos_from
    return {
        "dosFrom": dos_from,
        "dosTo": dos_to,
        "docDosFrom": _fmt_dos_display(
            row.get("doc_dos_from_iso") or row.get("doc_dos_from") or ""
        ),
        "docDosTo": _fmt_dos_display(row.get("doc_dos_to_iso") or row.get("doc_dos_to") or ""),
    }


def _read_dos_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None}
            if row:
                rows.append(row)
        return rows


def _index_dos_rows(rows: list[dict[str, str]], chart_name: str) -> dict[str, dict[str, str | None]]:
    """Map page filename / page number → DOS fields for one chart."""
    by_key: dict[str, dict[str, str | None]] = {}
    for row in rows:
        cname = (row.get("chart_name") or chart_name).strip()
        if cname and cname != chart_name:
            continue
        fields = _dos_row_fields(row)
        page_name = (row.get("page_name") or "").strip()
        if page_name:
            by_key[page_name.lower()] = fields
            by_key[Path(page_name).name.lower()] = fields
        raw_num = (row.get("page_number") or "").strip()
        if raw_num.isdigit():
            by_key[f"#{raw_num}"] = fields
    return by_key


def _overlay_dos_on_pages(
    pages: list[ImagingPageResult],
    dos_by_key: dict[str, dict[str, str | None]],
) -> list[ImagingPageResult]:
    if not dos_by_key:
        return pages
    out: list[ImagingPageResult] = []
    for page in pages:
        hit = (
            dos_by_key.get(page.fileName.lower())
            or dos_by_key.get(Path(page.fileName).name.lower())
            or dos_by_key.get(f"#{page.pageNumber}")
        )
        if not hit:
            out.append(page)
            continue
        out.append(
            page.model_copy(
                update={
                    "dosFrom": hit.get("dosFrom"),
                    "dosTo": hit.get("dosTo"),
                    "docDosFrom": hit.get("docDosFrom"),
                    "docDosTo": hit.get("docDosTo"),
                }
            )
        )
    return out


def _index_hw_rows(
    rows: list[dict[str, str]], chart_name: str
) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        cname = (row.get("chart_name") or chart_name).strip()
        if cname and cname != chart_name:
            continue
        label = (row.get("handwritten_or_printed") or row.get("type") or "").strip()
        if not label:
            continue
        conf_raw = (row.get("confidence") or "").strip()
        conf: float | None = None
        if conf_raw:
            try:
                conf = float(conf_raw)
                if conf > 1:
                    conf = conf / 100.0
            except ValueError:
                conf = None
        fields: dict[str, Any] = {
            "handwrittenOrPrinted": label,
            "handwrittenOrPrintedConfidence": conf,
        }
        page_name = (row.get("page_name") or "").strip()
        if page_name:
            by_key[page_name.lower()] = fields
            by_key[Path(page_name).name.lower()] = fields
        raw_num = (row.get("page_number") or "").strip()
        if raw_num.isdigit():
            by_key[f"#{raw_num}"] = fields
    return by_key


def _overlay_hw_on_pages(
    pages: list[ImagingPageResult],
    hw_by_key: dict[str, dict[str, Any]],
) -> list[ImagingPageResult]:
    if not hw_by_key:
        return pages
    out: list[ImagingPageResult] = []
    for page in pages:
        hit = (
            hw_by_key.get(page.fileName.lower())
            or hw_by_key.get(Path(page.fileName).name.lower())
            or hw_by_key.get(f"#{page.pageNumber}")
        )
        if not hit:
            out.append(page)
            continue
        out.append(page.model_copy(update=hit))
    return out


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
        """True if imaging JSON or any pipeline CSV overlay exists for this chart."""
        path = self._imaging_path(folder_dir)
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            pass
        imaging_dir = folder_dir / "imaging"
        if imaging_dir.is_dir():
            for name in (
                f"{folder_dir.name}_dos.csv",
                f"{folder_dir.name}_hw_printed.csv",
                f"{folder_dir.name}_rotation.csv",
                f"{folder_dir.name}_member_extraction.csv",
            ):
                p = imaging_dir / name
                if p.is_file() and p.stat().st_size > 0:
                    return True
        # Combined pack outputs (header-only files don't count as "has imaging")
        from app.services.imaging_overlays import collect_rows

        chart = folder_dir.name
        checks = [
            collect_rows(
                folder_dir=folder_dir,
                data_root=self.data_root,
                per_chart_name=f"{chart}_dos.csv",
                combined_rel=(
                    "02-imaging-pipeline",
                    "dos-extraction",
                    "output",
                    "dos_extraction.csv",
                ),
                chart_name=chart,
            ),
            collect_rows(
                folder_dir=folder_dir,
                data_root=self.data_root,
                per_chart_name=f"{chart}_hw_printed.csv",
                combined_rel=("01-ocr-extraction", "output", "hw_printed.csv"),
                chart_name=chart,
            ),
            collect_rows(
                folder_dir=folder_dir,
                data_root=self.data_root,
                per_chart_name=f"{chart}_rotation.csv",
                combined_rel=(
                    "02-imaging-pipeline",
                    "rotation-orientation",
                    "output",
                    "rotation.csv",
                ),
                chart_name=chart,
            ),
            collect_rows(
                folder_dir=folder_dir,
                data_root=self.data_root,
                per_chart_name=f"{chart}_member_extraction.csv",
                combined_rel=(
                    "02-imaging-pipeline",
                    "member-verification",
                    "output",
                    "member_extraction_results.csv",
                ),
                chart_name=chart,
            ),
        ]
        return any(bool(rows) for rows in checks)

    def _imaging_processed_count(self, folder_dir: Path, page_count: int) -> int:
        """Pages with real overlay data; avoid fabricating counts."""
        if page_count == 0 or not self._has_imaging(folder_dir):
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

    def _empty_imaging_pages(
        self, folder_dir: Path, pages: list[tuple[int, Path]]
    ) -> list[ImagingPageResult]:
        """Page skeletons only — extraction fields filled only from pipeline CSVs."""
        from app.services.imaging_overlays import empty_imaging_pages

        return empty_imaging_pages(pages)

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
        return self._empty_imaging_pages(folder_dir, self._page_files(folder_dir))

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
        has_imaging = self._has_imaging(folder_dir)
        page_summaries = [
            PageSummary(
                page_number=num,
                filename=path.name,
                image_url=f"/api/folders/{folder_id}/pages/{num}/image",
                has_preliminary_ocr=has_prelim,
                has_final1_ocr=has_final1,
                has_final2_ocr=has_final2,
                has_imaging=has_imaging,
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

    def _dos_overlay_for_folder(self, folder_dir: Path) -> dict[str, dict[str, str | None]]:
        """Prefer imaging/<chart>_dos.csv, else combined dos_extraction.csv for this chart."""
        chart = folder_dir.name
        per_chart = folder_dir / "imaging" / f"{chart}_dos.csv"
        rows = _read_dos_csv_rows(per_chart)
        if not rows:
            # monorepo: …/05-imaging-ui/data/folders → …/02-imaging-pipeline/…
            combined = (
                self.data_root.parent.parent.parent
                / "02-imaging-pipeline"
                / "dos-extraction"
                / "output"
                / "dos_extraction.csv"
            )
            # nested layout fallback: imaging-ui repo without numbered packs
            if not combined.is_file():
                combined = (
                    self.data_root.parent.parent
                    / "02-imaging-pipeline"
                    / "dos-extraction"
                    / "output"
                    / "dos_extraction.csv"
                )
            rows = [
                r
                for r in _read_dos_csv_rows(combined)
                if (r.get("chart_name") or "").strip() == chart
            ]
        return _index_dos_rows(rows, chart)

    def _hw_overlay_for_folder(self, folder_dir: Path) -> dict[str, dict[str, Any]]:
        """Prefer imaging/<chart>_hw_printed.csv, else 01-ocr-extraction/output/hw_printed.csv."""
        chart = folder_dir.name
        per_chart = folder_dir / "imaging" / f"{chart}_hw_printed.csv"
        rows = _read_dos_csv_rows(per_chart)
        if not rows:
            combined = (
                self.data_root.parent.parent.parent
                / "01-ocr-extraction"
                / "output"
                / "hw_printed.csv"
            )
            if not combined.is_file():
                combined = (
                    self.data_root.parent.parent
                    / "01-ocr-extraction"
                    / "output"
                    / "hw_printed.csv"
                )
            rows = [
                r
                for r in _read_dos_csv_rows(combined)
                if (r.get("chart_name") or "").strip() == chart
            ]
        return _index_hw_rows(rows, chart)

    def get_imaging(self, folder_id: str) -> ImagingDocumentResponse:
        """Build imaging rows from pipeline CSVs only (no dummy fabricated values)."""
        from app.services.imaging_overlays import (
            collect_rows,
            empty_imaging_pages,
            index_dos_rows,
            index_hw_rows,
            index_member_extraction_rows,
            index_rotation_rows,
            load_verification,
            overlay_fields,
            read_csv_rows,
            monorepo_root_from_data,
        )

        folder_dir = self._folder_dir(folder_id)
        pages = self._page_files(folder_dir)
        path = self._imaging_path(folder_dir)
        chart = folder_dir.name

        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid imaging JSON in {path.name}: {exc}",
                ) from exc
            imaging_pages = self._parse_imaging_pages(data, folder_dir)
            manifest = self._parse_imaging_manifest(data, folder_id)
        else:
            imaging_pages = empty_imaging_pages(pages)
            manifest = self._manifest_for_folder(folder_id)

        imaging_pages = overlay_fields(
            imaging_pages,
            index_dos_rows(
                collect_rows(
                    folder_dir=folder_dir,
                    data_root=self.data_root,
                    per_chart_name=f"{chart}_dos.csv",
                    combined_rel=(
                        "02-imaging-pipeline",
                        "dos-extraction",
                        "output",
                        "dos_extraction.csv",
                    ),
                    chart_name=chart,
                ),
                chart,
            ),
        )
        imaging_pages = overlay_fields(
            imaging_pages,
            index_hw_rows(
                collect_rows(
                    folder_dir=folder_dir,
                    data_root=self.data_root,
                    per_chart_name=f"{chart}_hw_printed.csv",
                    combined_rel=("01-ocr-extraction", "output", "hw_printed.csv"),
                    chart_name=chart,
                ),
                chart,
            ),
        )
        imaging_pages = overlay_fields(
            imaging_pages,
            index_rotation_rows(
                collect_rows(
                    folder_dir=folder_dir,
                    data_root=self.data_root,
                    per_chart_name=f"{chart}_rotation.csv",
                    combined_rel=(
                        "02-imaging-pipeline",
                        "rotation-orientation",
                        "output",
                        "rotation.csv",
                    ),
                    chart_name=chart,
                ),
                chart,
            ),
        )
        imaging_pages = overlay_fields(
            imaging_pages,
            index_member_extraction_rows(
                collect_rows(
                    folder_dir=folder_dir,
                    data_root=self.data_root,
                    per_chart_name=f"{chart}_member_extraction.csv",
                    combined_rel=(
                        "02-imaging-pipeline",
                        "member-verification",
                        "output",
                        "member_extraction_results.csv",
                    ),
                    chart_name=chart,
                ),
                chart,
            ),
        )

        ver_rows = collect_rows(
            folder_dir=folder_dir,
            data_root=self.data_root,
            per_chart_name=f"{chart}_member_verification.csv",
            combined_rel=(
                "02-imaging-pipeline",
                "member-verification",
                "output",
                "member_verification_summary.csv",
            ),
            chart_name=chart,
        )
        # also allow dropping the excel export at pack root output
        if not ver_rows:
            alt = (
                monorepo_root_from_data(self.data_root)
                / "02-imaging-pipeline"
                / "member-verification"
                / "output"
                / "member_verification_summary.csv"
            )
            ver_rows = [
                r
                for r in read_csv_rows(alt)
                if (r.get("chart_id") or r.get("chart_name") or "").strip()
                in {chart, chart.split("_", 1)[0]}
                or chart.startswith((r.get("chart_id") or "") + "_")
            ]

        verification = load_verification(ver_rows, chart)

        return ImagingDocumentResponse(
            folder_id=folder_id,
            manifest=manifest,
            verification=verification,
            pages=imaging_pages,
        )
