"""Junk classification codes + text rules — ported from document-processing junk/runner.py."""

from __future__ import annotations

import hashlib
import re

from blank import detect_blank_page, is_declared_blank_page
from cover import detect_cover_page
from invoice import detect_invoice_page

CODE_MAIN = 0
CODE_BLANK = 1
CODE_INVOICE = 2
CODE_COVER = 3
CODE_DUPLICATE = 4

CLASSIFICATION_LABELS = {
    CODE_MAIN: "Main",
    CODE_BLANK: "Blank",
    CODE_INVOICE: "Invoice",
    CODE_COVER: "Cover",
    CODE_DUPLICATE: "Duplicate",
}

_MIN_FINGERPRINT_CHARS = 50

DEFAULT_SETTINGS = {
    "blank_detection": True,
    "invoice_detection": True,
    "cover_fax_detection": True,
    "duplicate_detection": True,
    "declared_blank_detection": True,
}


def classify_text(
    full_text: str,
    *,
    settings: dict | None = None,
) -> tuple[int, str]:
    """Return (code, reason). Priority: blank → declared blank → invoice → cover."""
    cfg = {**DEFAULT_SETTINGS, **(settings or {})}

    if cfg.get("blank_detection") and detect_blank_page(full_text):
        return CODE_BLANK, "blank_ocr"
    if cfg.get("declared_blank_detection") and is_declared_blank_page(text=full_text):
        return CODE_BLANK, "declared_blank"
    if cfg.get("invoice_detection") and detect_invoice_page(full_text):
        return CODE_INVOICE, "invoice"
    if cfg.get("cover_fax_detection") and detect_cover_page(full_text):
        return CODE_COVER, "cover"
    return CODE_MAIN, ""


def fingerprint(text: str) -> str | None:
    """SHA-256 of whitespace-stripped lowercase OCR; None if too short."""
    norm = re.sub(r"\s+", "", text or "").lower()
    if len(norm) < _MIN_FINGERPRINT_CHARS:
        return None
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def classification_confidence(code: int, *, blank_via_image: bool = False) -> float | None:
    if code <= 0:
        return None
    if code == CODE_BLANK:
        return 0.95 if blank_via_image else 0.9
    if code == CODE_DUPLICATE:
        return 0.99
    return 0.85
