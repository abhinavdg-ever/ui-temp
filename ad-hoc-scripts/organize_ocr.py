#!/usr/bin/env python3
"""
Copy OCR output files into ocr/ under each matching document folder in the images root.

You can pass separate roots for each OCR kind:

  --prelim   Preliminary (Tess)
  --final1   Final (OSS)
  --final2   Final (AzDocInt)

Or a single combined --ocr-root (legacy) where each document folder holds all kinds.

If a source file is not already named <folder>_prelim.txt (or _final1 / _final2),
the script still writes the correctly suffixed name into images/<folder>/ocr/.

Expected layouts (any combination of --prelim / --final1 / --final2):

  <prelim_root>/<folder_name>/*.txt
  <final1_root>/<folder_name>/*.txt
  <final2_root>/<folder_name>/*.txt

  # also accepted: a single .txt sitting directly as
  # <prelim_root>/<folder_name>.txt

Result:
  <images_root>/<folder_name>/ocr/
    <folder_name>_prelim.txt
    <folder_name>_final1.txt
    <folder_name>_final2.txt

Usage:
  python organize_ocr.py \\
    --images-root "/path/to/images" \\
    --prelim "/path/to/prelim" \\
    --final1 "/path/to/final1" \\
    --final2 "/path/to/final2"

  python organize_ocr.py --images-root "/path/to/images" --ocr-root "/path/to/ocr" --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

KIND_SUFFIXES = ("prelim", "final1", "final2")

# Used only for --ocr-root (combined) classification
KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prelim", re.compile(r"(^|[_\-.])prelim(inary)?([_\-.]|$)", re.I)),
    ("final1", re.compile(r"(^|[_\-.])(final1|final_?oss|oss)([_\-.]|$)", re.I)),
    ("final2", re.compile(r"(^|[_\-.])(final2|final_?(az|azure|azdoc|azdocint)|azdocint|azure)([_\-.]|$)", re.I)),
]


def has_kind_suffix(name: str, kind: str) -> bool:
    return name.lower().endswith(f"_{kind}.txt")


def classify_ocr_file(path: Path) -> str | None:
    lower = path.name.lower()
    for suffix in ("_prelim.txt", "_final1.txt", "_final2.txt"):
        if lower.endswith(suffix):
            return suffix[1:-4]
    for suffix, pattern in KIND_PATTERNS:
        if pattern.search(path.stem):
            return suffix
    return None


def iter_txt_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for entry in folder.rglob("*"):
        if not entry.is_file() or entry.name.startswith("._"):
            continue
        if entry.suffix.lower() == ".txt":
            files.append(entry)
    return files


def pick_source_txt(folder_or_file: Path, kind: str) -> Path | None:
    """Pick the best OCR .txt for a known kind from a folder or a single file."""
    if folder_or_file.is_file():
        return folder_or_file if folder_or_file.suffix.lower() == ".txt" else None

    if not folder_or_file.is_dir():
        return None

    txts = iter_txt_files(folder_or_file)
    if not txts:
        return None

    # Prefer already-suffixed names
    for path in txts:
        if has_kind_suffix(path.name, kind):
            return path

    # Prefer names that classify as this kind
    for path in txts:
        if classify_ocr_file(path) == kind:
            return path

    # Fallback: single txt in the folder (common when kind root already separates kinds)
    if len(txts) == 1:
        return txts[0]

    # Prefer raw_text.txt / ocr.txt style names
    preferred = {"raw_text.txt", "ocr.txt", "text.txt", "output.txt"}
    for path in txts:
        if path.name.lower() in preferred:
            return path

    # Last resort: first txt by name
    return sorted(txts, key=lambda p: p.name.lower())[0]


def collect_from_kind_root(kind_root: Path, kind: str) -> dict[str, Path]:
    """Map folder_name -> source txt under a kind-specific root."""
    found: dict[str, Path] = {}
    if not kind_root.is_dir():
        return found

    for entry in sorted(kind_root.iterdir(), key=lambda p: p.name.lower()):
        if entry.name.startswith(".") or entry.name.startswith("._"):
            continue

        if entry.is_dir():
            src = pick_source_txt(entry, kind)
            if src:
                found[entry.name] = src
            continue

        # Loose file: folder_name.txt or folder_name_prelim.txt
        if entry.is_file() and entry.suffix.lower() == ".txt":
            stem = entry.stem
            # Strip trailing _kind if present so key matches images folder name
            suffix = f"_{kind}"
            if stem.lower().endswith(suffix):
                folder_name = stem[: -len(suffix)]
            else:
                folder_name = stem
            if folder_name and folder_name not in found:
                found[folder_name] = entry

    return found


def collect_from_combined_root(ocr_root: Path) -> dict[str, dict[str, Path]]:
    """Map folder_name -> {kind: path} for a combined OCR root."""
    result: dict[str, dict[str, Path]] = {}
    for entry in sorted(ocr_root.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        mapping: dict[str, Path] = {}
        for path in iter_txt_files(entry):
            kind = classify_ocr_file(path)
            if kind and kind not in mapping:
                mapping[kind] = path
        # If nothing classified but exactly one txt, leave unset (can't guess kind)
        if mapping:
            result[entry.name] = mapping
    return result


def copy_kind(
    *,
    images_root: Path,
    folder_name: str,
    kind: str,
    src: Path,
    dry_run: bool,
) -> bool:
    dest_folder = images_root / folder_name
    if not dest_folder.is_dir():
        print(f"[{folder_name}] SKIP {kind} — no matching folder under images root")
        return False

    ocr_dir = dest_folder / "ocr"
    dest_name = f"{folder_name}_{kind}.txt"
    dest = ocr_dir / dest_name

    note = ""
    if not has_kind_suffix(src.name, kind):
        note = f" (added _{kind} suffix)"

    print(f"[{folder_name}] COPY {src} -> ocr/{dest_name}{note}")
    if dry_run:
        return True

    ocr_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy OCR outputs into images/<folder>/ocr/ as "
            "<folder>_prelim.txt / _final1.txt / _final2.txt. "
            "Pass --prelim / --final1 / --final2 roots, and/or legacy --ocr-root."
        )
    )
    parser.add_argument(
        "--images-root",
        required=True,
        help="Root folder containing document subfolders (destination)",
    )
    parser.add_argument(
        "--prelim",
        default=None,
        help="Root folder of Preliminary (Tess) OCR outputs",
    )
    parser.add_argument(
        "--final1",
        default=None,
        help="Root folder of Final (OSS) OCR outputs",
    )
    parser.add_argument(
        "--final2",
        default=None,
        help="Root folder of Final (AzDocInt) OCR outputs",
    )
    parser.add_argument(
        "--ocr-root",
        default=None,
        help="Optional combined OCR root (legacy). Document subfolders hold mixed kinds.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without changing files",
    )
    args = parser.parse_args()

    images_root = Path(args.images_root).expanduser().resolve()
    if not images_root.is_dir():
        print(f"ERROR: images root not found: {images_root}")
        return 1

    kind_roots: list[tuple[str, Path]] = []
    for kind, raw in (
        ("prelim", args.prelim),
        ("final1", args.final1),
        ("final2", args.final2),
    ):
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            print(f"ERROR: {kind} root not found: {path}")
            return 1
        kind_roots.append((kind, path))

    ocr_root = Path(args.ocr_root).expanduser().resolve() if args.ocr_root else None
    if ocr_root is not None and not ocr_root.is_dir():
        print(f"ERROR: OCR root not found: {ocr_root}")
        return 1

    if not kind_roots and ocr_root is None:
        print("ERROR: provide at least one of --prelim, --final1, --final2, or --ocr-root")
        return 1

    copied = 0
    skipped = 0

    # Kind-specific roots
    for kind, root in kind_roots:
        mapping = collect_from_kind_root(root, kind)
        if not mapping:
            print(f"[{kind}] No OCR folders/files under {root}")
            continue
        for folder_name, src in sorted(mapping.items(), key=lambda x: x[0].lower()):
            ok = copy_kind(
                images_root=images_root,
                folder_name=folder_name,
                kind=kind,
                src=src,
                dry_run=args.dry_run,
            )
            if ok:
                copied += 1
            else:
                skipped += 1

    # Combined legacy root
    if ocr_root is not None:
        combined = collect_from_combined_root(ocr_root)
        if not combined:
            print(f"[ocr-root] No recognizable OCR folders under {ocr_root}")
        for folder_name, kinds in sorted(combined.items(), key=lambda x: x[0].lower()):
            for kind, src in sorted(kinds.items()):
                ok = copy_kind(
                    images_root=images_root,
                    folder_name=folder_name,
                    kind=kind,
                    src=src,
                    dry_run=args.dry_run,
                )
                if ok:
                    copied += 1
                else:
                    skipped += 1

    print(
        f"Done. {'Would copy' if args.dry_run else 'Copied'} {copied} file(s); "
        f"skipped {skipped}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
