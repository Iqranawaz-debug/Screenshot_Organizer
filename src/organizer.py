"""Plan and (optionally) apply screenshot organization, safely."""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from src.duplicate_detector import HashIndex, build_destination_index, file_sha256
from config import Settings
from src.categorizer import categorize
from src.date_resolver import resolve_capture_date
from src.filename_generator import build_filename, unique_path
from src.ocr_engine import extract_text
from src.screenshot_detector import is_inside
from src.title_generators import DEFAULT_TITLE_GENERATOR, TitleGenerator
from src.text_analyzer import content_text, category_interface_hint
logger = logging.getLogger(__name__)


class FolderConfigError(ValueError):
    """Source and destination folders are unsafe to use together."""


class ConfirmationRequiredError(RuntimeError):
    """Moving files was requested without explicit confirmation."""


@dataclass
class PlannedItem:
    source: Path
    status: str = "planned"       # planned | copied | moved | skipped | error
    message: str = ""
    new_name: str = ""
    title: str | None = None
    title_source: str = ""
    date_value: date | None = None
    date_source: str = ""
    category: str = ""
    category_reason: str = ""
    destination: Path | None = None
    ocr_text: str = ""
    file_hash: str = ""
    title_reason: str = ""

    @property
    def original_name(self) -> str:
        return self.source.name


def validate_folders(source: Path, destination: Path) -> None:
    """Reject identical or nested folders (they cause re-processing loops)."""
    src, dst = source.resolve(), destination.resolve()
    if src == dst:
        raise FolderConfigError("Source and destination must be different folders.")
    if dst.is_relative_to(src):
        raise FolderConfigError(
            f"The destination ({dst}) is inside the source folder. "
            "Choose a destination outside the source."
        )
    if src.is_relative_to(dst):
        raise FolderConfigError(
            f"The source ({src}) is inside the destination folder. "
            "Choose a source outside the destination."
        )


def safe_copy(source: Path, destination: Path) -> Path:
    """Copy a file without ever overwriting. Returns the final path used.

    The target is opened in exclusive-create mode ('xb'), so an existing file
    is never touched; on a clash the next free _02, _03... name is used.
    """
    target = destination
    while True:
        created = False
        try:
            with open(source, "rb") as src_file, open(target, "xb") as dst_file:
                created = True
                shutil.copyfileobj(src_file, dst_file)
            break
        except FileExistsError:
            target = unique_path(target.parent, target.name)
        except OSError:
            if created:  # remove only the partial file we just created
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove partial file %s", target)
            raise
    try:
        shutil.copystat(source, target)  # keep original timestamps
    except OSError as exc:
        logger.warning("Could not copy file times to %s: %s", target, exc)
    return target


def _plan_one(
    path: Path,
    destination: Path,
    settings: Settings,
    reserved_by_folder: dict[Path, set[str]],
    *,
    title_generator: TitleGenerator | None = None,
) -> PlannedItem:
    item = PlannedItem(source=path)

    result = extract_text(path, settings)  # raises only if Tesseract is missing
    analysis = (title_generator or DEFAULT_TITLE_GENERATOR).generate(result, settings)
    try:
        date_info = resolve_capture_date(path)
    except OSError as exc:
        item.status, item.message = "error", f"Cannot read file date: {exc}"
        return item

    category = categorize(content_text(result), settings, image_path=path,
                          interface_hint=category_interface_hint(result))
    filename = build_filename(analysis.title, date_info.value, path.suffix, settings)

    folder = destination / category.category
    reserved = reserved_by_folder.setdefault(folder, set())
    target = unique_path(folder, filename, reserved)
    reserved.add(target.name.lower())

    item.new_name = target.name
    item.destination = target
    item.title = analysis.title
    item.title_source = analysis.source
    item.title_reason = analysis.reason
    item.date_value = date_info.value
    item.date_source = date_info.source
    item.category = category.category
    item.category_reason = category.reason
    item.ocr_text = result.full_text
    if analysis.source == "fallback":
        item.message = f"Neutral filename used: {analysis.reason}"
    return item


def plan_screenshots(
    sources: list[Path],
    destination: Path,
    settings: Settings,
    index: HashIndex | None = None,
    *,
    title_generator: TitleGenerator | None = None,
) -> list[PlannedItem]:
    """Work out what would happen to each file. Touches nothing on disk.

    Files whose content already exists in the destination (or appeared earlier
    in this batch) are skipped before OCR, so re-running never creates copies.
    """
    items: list[PlannedItem] = []
    reserved_by_folder: dict[Path, set[str]] = {}
    if index is None:
        index = build_destination_index(destination, settings.supported_extensions)

    for path in sources:
        if is_inside(path, destination):
            items.append(PlannedItem(
                source=path, status="skipped",
                message="Already inside the destination folder.",
            ))
            continue

        try:
            digest = file_sha256(path)
        except OSError as exc:
            items.append(PlannedItem(
                source=path, status="error",
                message=f"Cannot read file: {exc}",
            ))
            continue

        existing = index.find(digest)
        if existing is not None:
            items.append(PlannedItem(
                source=path, status="skipped", file_hash=digest,
                message=f"Duplicate of {existing}",
            ))
            continue

        item = _plan_one(
            path, destination, settings, reserved_by_folder, title_generator=title_generator
        )
        item.file_hash = digest
        if item.status == "planned" and item.destination is not None:
            index.add(digest, item.destination)  # catches duplicates inside this batch
        items.append(item)
    return items


def execute_plan(
    items: list[PlannedItem],
    *,
    mode: str = "copy",
    dry_run: bool = True,
    confirm_move: bool = False,
) -> list[PlannedItem]:
    """Apply a plan. Defaults are the safest: dry-run and copy."""
    if mode not in ("copy", "move"):
        raise ValueError("mode must be 'copy' or 'move'")
    if dry_run:
        return items
    if mode == "move" and not confirm_move:
        raise ConfirmationRequiredError(
            "Moving files requires explicit confirmation (confirm_move=True)."
        )

    for item in items:
        if item.status != "planned" or item.destination is None:
            continue
        try:
            item.destination.parent.mkdir(parents=True, exist_ok=True)
            final = safe_copy(item.source, item.destination)
            item.destination, item.new_name = final, final.name
            item.status = "copied"
            logger.info("Copied %s -> %s", item.source, final)

            if mode == "move":
                if final.stat().st_size != item.source.stat().st_size:
                    raise OSError("Copy size mismatch; original kept.")
                try:
                    item.source.unlink()
                    item.status = "moved"
                    logger.info("Removed original after verified copy: %s", item.source)
                except OSError as exc:
                    item.message = f"Copied, but the original could not be removed: {exc}"
        except PermissionError as exc:
            item.status = "error"
            item.message = f"Permission denied or file locked: {exc}"
            logger.warning("Permission error for %s: %s", item.source, exc)
        except OSError as exc:
            item.status, item.message = "error", str(exc)
            logger.warning("Failed for %s: %s", item.source, exc)
    return items
