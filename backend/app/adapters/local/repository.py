from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.adapters.base import FolderRepository
from app.core.schemas import FolderDetail, FolderSummary, OcrTextResponse, PageSummary

PAGE_RE = re.compile(r"^page_(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
PLAIN_NUM_RE = re.compile(r"^(\d+)\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)
IMAGE_RE = re.compile(r"\.(jpe?g|png|webp|tif{1,2})$", re.IGNORECASE)

KIND_TO_SUFFIX = {
    "preliminary": "prelim",
    "final": "final",
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


class LocalFolderRepository(FolderRepository):
    """Reads document folders from a local filesystem tree.

    Layout per folder:
      pages/1.jpg …
      ocr/<folder_name>_prelim.txt   # sections: ===== 1.jpg =====
      ocr/<folder_name>_final.txt
    """

    def __init__(self, data_root: Path):
        self.data_root = data_root

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
            raise HTTPException(status_code=400, detail="kind must be preliminary or final")
        return folder_dir / "ocr" / f"{folder_dir.name}_{suffix}.txt"

    def _has_ocr(self, folder_dir: Path, kind: str) -> bool:
        path = self._ocr_path(folder_dir, kind)
        try:
            return path.is_file() and path.stat().st_size > 0
        except OSError:
            return False

    def _page_files(self, folder_dir: Path) -> list[tuple[int, Path]]:
        pages_dir = folder_dir / "pages"
        if not pages_dir.is_dir():
            return []
        numbered: list[tuple[int, Path]] = []
        other: list[Path] = []
        for entry in pages_dir.iterdir():
            if not entry.is_file() or entry.name.startswith("._"):
                continue
            if not IMAGE_RE.search(entry.name):
                continue
            num = _page_num_from_name(entry.name)
            if num is not None:
                numbered.append((num, entry))
            else:
                other.append(entry)
        numbered.sort(key=lambda x: x[0])
        # Unnumbered images follow, sorted by name, after the highest number
        next_num = (numbered[-1][0] + 1) if numbered else 1
        other.sort(key=lambda p: p.name.lower())
        for path in other:
            numbered.append((next_num, path))
            next_num += 1
        return numbered

    def _ocr_processed_count(self, folder_dir: Path, page_count: int) -> int:
        """If a folder-level OCR file exists, treat all pages as OCR-processed."""
        if page_count == 0:
            return 0
        if self._has_ocr(folder_dir, "preliminary") or self._has_ocr(folder_dir, "final"):
            return page_count
        return 0

    def _touch_paths(self, folder_dir: Path, pages: list[tuple[int, Path]]) -> list[Path]:
        paths = [folder_dir, *(p for _, p in pages)]
        for kind in ("preliminary", "final"):
            ocr = self._ocr_path(folder_dir, kind)
            if ocr.is_file():
                paths.append(ocr)
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
                    imaging_processed=0,
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
        has_final = self._has_ocr(folder_dir, "final")
        page_summaries = [
            PageSummary(
                page_number=num,
                filename=path.name,
                image_url=f"/api/folders/{folder_id}/pages/{num}/image",
                has_preliminary_ocr=has_prelim,
                has_final_ocr=has_final,
            )
            for num, path in pages
        ]
        return FolderDetail(
            id=folder_id,
            name=folder_dir.name,
            page_count=len(pages),
            ocr_processed=self._ocr_processed_count(folder_dir, len(pages)),
            imaging_processed=0,
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
        folder_dir = self._folder_dir(folder_id)
        path = self._ocr_path(folder_dir, kind)
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"No {kind} OCR file ({path.name}) in {folder_id}",
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        return OcrTextResponse(
            folder_id=folder_id,
            kind="preliminary" if kind == "preliminary" else "final",
            text=text,
        )


