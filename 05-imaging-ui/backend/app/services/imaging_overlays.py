"""Load imaging pipeline CSV outputs and overlay onto page rows (no dummy values).

Sources (monorepo packs under repo root next to 05-imaging-ui):
  01-ocr-extraction/output/hw_printed.csv
  02-imaging-pipeline/dos-extraction/output/dos_extraction.csv
  02-imaging-pipeline/rotation-orientation/output/rotation.csv
  02-imaging-pipeline/member-verification/output/member_extraction_results.csv
  02-imaging-pipeline/member-verification/output/member_verification_summary.csv

Per-chart overrides under data/folders/<chart>/imaging/ are preferred when present.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.core.schemas import ImagingPageResult, ImagingVerificationDetails


def read_csv_rows(path: Path) -> list[dict[str, str]]:
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


def monorepo_root_from_data(data_root: Path) -> Path:
    """data/folders → 05-imaging-ui → monorepo root."""
    return data_root.parent.parent.parent


def chart_id_key(chart_name: str) -> str:
    """52743839_44976074 → 52743839; plain names unchanged."""
    name = chart_name.strip()
    if "_" in name and name.split("_", 1)[0].isdigit():
        return name.split("_", 1)[0]
    return name


def _fmt_dos_display(raw: str | date | None) -> str | None:
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


def dos_row_fields(row: dict[str, str]) -> dict[str, str | None]:
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


def _parse_float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if not value or value.upper() in {"N/A", "NA", "NULL", "NONE"}:
        return None
    try:
        num = float(value)
    except ValueError:
        return None
    if num > 1.0 and num <= 100.0:
        return round(num / 100.0, 4)
    return num


def _parse_bool(raw: str | None) -> bool | None:
    value = (raw or "").strip().lower()
    if not value:
        return None
    if value in {"1", "true", "t", "yes", "y"}:
        return True
    if value in {"0", "false", "f", "no", "n"}:
        return False
    return None


def empty_imaging_pages(pages: list[tuple[int, Path]]) -> list[ImagingPageResult]:
    """Skeleton rows only — all extraction fields stay null until CSV overlay."""
    return [
        ImagingPageResult(pageNumber=num, fileName=path.name) for num, path in pages
    ]


def page_has_imaging(page: ImagingPageResult) -> bool:
    return any(
        [
            page.memberName,
            page.memberDob,
            page.memberId,
            page.handwrittenOrPrinted,
            page.orientationAngle is not None,
            page.tiltAngle is not None,
            page.mirrored is not None,
            page.dosFrom,
            page.dosTo,
            page.pageType,
        ]
    )


def _hit_for_page(
    by_key: dict[str, dict[str, Any]], page: ImagingPageResult
) -> dict[str, Any] | None:
    return (
        by_key.get(page.fileName.lower())
        or by_key.get(Path(page.fileName).name.lower())
        or by_key.get(f"#{page.pageNumber}")
        or by_key.get(Path(page.fileName).stem.lower())
    )


def overlay_fields(
    pages: list[ImagingPageResult],
    by_key: dict[str, dict[str, Any]],
) -> list[ImagingPageResult]:
    if not by_key:
        return pages
    out: list[ImagingPageResult] = []
    for page in pages:
        hit = _hit_for_page(by_key, page)
        if not hit:
            out.append(page)
            continue
        out.append(page.model_copy(update=hit))
    return out


def index_dos_rows(rows: list[dict[str, str]], chart_name: str) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        cname = (row.get("chart_name") or chart_name).strip()
        if cname and cname != chart_name:
            continue
        fields = dos_row_fields(row)
        _put_page_keys(by_key, row, fields)
    return by_key


def index_hw_rows(rows: list[dict[str, str]], chart_name: str) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        cname = (row.get("chart_name") or chart_name).strip()
        if cname and cname != chart_name:
            continue
        label = (row.get("handwritten_or_printed") or row.get("type") or "").strip()
        if not label:
            continue
        fields: dict[str, Any] = {
            "handwrittenOrPrinted": label,
            "handwrittenOrPrintedConfidence": _parse_float(row.get("confidence")),
        }
        _put_page_keys(by_key, row, fields)
    return by_key


def index_rotation_rows(
    rows: list[dict[str, str]], chart_name: str
) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        folder = (row.get("folder") or row.get("chart_name") or "").strip()
        if folder and folder != chart_name:
            continue
        filename = (row.get("filename") or row.get("page_name") or "").strip()
        fields: dict[str, Any] = {
            "orientationAngle": _parse_float(row.get("rotation_deg") or row.get("orientation_angle")),
            "tiltAngle": _parse_float(row.get("tilt_angle_deg") or row.get("tilt_angle")),
            "mirrored": _parse_bool(row.get("mirrored")),
            "pageQualityConfidence": _parse_float(row.get("confidence")),
        }
        # drop empty updates
        fields = {k: v for k, v in fields.items() if v is not None}
        if not fields:
            continue
        if filename:
            by_key[filename.lower()] = fields
            by_key[Path(filename).name.lower()] = fields
            stem = Path(filename).stem
            by_key[stem.lower()] = fields
            if stem.isdigit():
                by_key[f"#{stem}"] = fields
        raw_num = (row.get("page_number") or "").strip()
        if raw_num.isdigit():
            by_key[f"#{raw_num}"] = fields
    return by_key


def index_member_extraction_rows(
    rows: list[dict[str, str]], chart_name: str
) -> dict[str, dict[str, Any]]:
    cid = chart_id_key(chart_name)
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_chart = (row.get("chart_id") or row.get("chart_name") or "").strip()
        if row_chart and row_chart not in {chart_name, cid}:
            # allow numeric chart_id matching folder prefix
            if not (chart_name.startswith(row_chart + "_") or chart_name == row_chart):
                continue
        name = (row.get("extracted_name") or "").strip()
        dob = (row.get("extracted_dob") or "").strip()
        member_id = (
            (row.get("matched_id") or "").strip()
            or (row.get("provided_id") or "").strip()
            or (row.get("external_member_id") or "").strip()
        )
        if name.upper() == "N/A":
            name = ""
        if dob.upper() == "N/A":
            dob = ""
        if member_id.upper() == "N/A":
            member_id = ""
        fields: dict[str, Any] = {
            "memberName": name or None,
            "memberDob": dob or None,
            "memberId": member_id or None,
            "memberConfidence": _parse_float(row.get("confidence")),
        }
        fields = {k: v for k, v in fields.items() if v is not None and v != ""}
        if not fields:
            continue
        page_name = (row.get("page_name") or "").strip()
        if page_name and page_name.upper() != "N/A":
            by_key[page_name.lower()] = fields
            # "1" → also key #1 and 1.jpg
            if page_name.isdigit():
                by_key[f"#{page_name}"] = fields
                by_key[f"{page_name}.jpg"] = fields
                by_key[f"{page_name}.png"] = fields
            by_key[Path(page_name).name.lower()] = fields
        raw_num = (row.get("page_number") or "").strip()
        if raw_num.isdigit():
            by_key[f"#{raw_num}"] = fields
    return by_key


def load_verification(
    rows: list[dict[str, str]], chart_name: str
) -> ImagingVerificationDetails | None:
    cid = chart_id_key(chart_name)
    for row in rows:
        row_chart = (row.get("chart_id") or row.get("chart_name") or "").strip()
        if row_chart and row_chart not in {chart_name, cid}:
            if not (chart_name.startswith(row_chart + "_") or chart_name == row_chart):
                continue
        status = (row.get("final_status") or "").strip() or None
        reason = (row.get("decision_reason") or "").strip() or None
        info = (row.get("matched_member_info") or "").strip() or None
        conf = _parse_float(row.get("matched_confidence"))
        pm = (row.get("pages_matched") or "").strip()
        pc = (row.get("pages_checked") or "").strip()
        return ImagingVerificationDetails(
            finalStatus=status,
            matchedMemberInfo=info,
            matchedConfidence=conf,
            pagesMatched=int(pm) if pm.isdigit() else None,
            pagesChecked=int(pc) if pc.isdigit() else None,
            decisionReason=reason,
        )
    return None


def _put_page_keys(
    by_key: dict[str, dict[str, Any]], row: dict[str, str], fields: dict[str, Any]
) -> None:
    page_name = (row.get("page_name") or row.get("filename") or "").strip()
    if page_name:
        by_key[page_name.lower()] = fields
        by_key[Path(page_name).name.lower()] = fields
        stem = Path(page_name).stem
        by_key[stem.lower()] = fields
        if stem.isdigit():
            by_key[f"#{stem}"] = fields
    raw_num = (row.get("page_number") or "").strip()
    if raw_num.isdigit():
        by_key[f"#{raw_num}"] = fields


def collect_rows(
    *,
    folder_dir: Path,
    data_root: Path,
    per_chart_name: str,
    combined_rel: tuple[str, ...],
    chart_name: str,
    chart_filter: str | None = None,
) -> list[dict[str, str]]:
    """Prefer per-chart imaging CSV, else combined pack output."""
    per_chart = folder_dir / "imaging" / per_chart_name
    rows = read_csv_rows(per_chart)
    if rows:
        return rows
    root = monorepo_root_from_data(data_root)
    combined = root.joinpath(*combined_rel)
    rows = read_csv_rows(combined)
    if not rows:
        return []
    key = chart_filter or chart_name
    cid = chart_id_key(chart_name)
    filtered: list[dict[str, str]] = []
    for row in rows:
        # detect which id column exists
        for col in ("chart_name", "folder", "chart_id"):
            val = (row.get(col) or "").strip()
            if not val:
                continue
            if val in {chart_name, key, cid} or chart_name.startswith(val + "_"):
                filtered.append(row)
                break
    return filtered
