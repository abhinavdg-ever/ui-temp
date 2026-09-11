"""Cover / fax keyword junk detection — ported from document-processing junk/cover.py."""

from __future__ import annotations

import re

COVER_KEYWORDS = [
    "e-request letter",
    "request letter",
    "packet may contain",
    "intended recipient",
    "audit fulfillment",
    "medical records attached",
    "transmission contains",
    "advantmed",
    "confidential medical records",
    "request for medical records",
    "fax transmission",
    "medical records transmittal",
    "medical records request",
    "facimile transmittal sheet",
    "transmittal sheet",
    "medical record request",
    "send record",
    "risk adjustment request",
    "provide all documentation",
    "provide documentation",
    "confidentiality",
]

_PATTERNS = [re.compile(rf"\b{re.escape(kw.lower())}\b") for kw in COVER_KEYWORDS]

_SINGLE_WORD_COVER = frozenset({"accept", "summary", "unaccept"})

_RECORD_TOC_MARKERS = (
    re.compile(r"\bpatient\s+medical\s+record\b", re.IGNORECASE),
    re.compile(r"\btotal\s+pages\b", re.IGNORECASE),
    re.compile(r"\b\d{1,4}\s+to\s+\d{1,4}\b", re.IGNORECASE),
)


def _is_record_toc_cover(text: str) -> bool:
    title, total_pages, page_range = _RECORD_TOC_MARKERS
    if not title.search(text):
        return False
    return bool(total_pages.search(text) or page_range.search(text))


def _is_single_word_cover(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", (text or "").lower()).strip()
    words = cleaned.split()
    return len(words) == 1 and words[0] in _SINGLE_WORD_COVER


def detect_cover_page(text: str) -> bool:
    if not text:
        return False
    if _is_single_word_cover(text):
        return True
    if _is_record_toc_cover(text):
        return True
    text_lower = text.lower()
    return any(pattern.search(text_lower) is not None for pattern in _PATTERNS)
