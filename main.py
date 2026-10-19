"""Command-line entry point. Everything is a preview unless --apply is given."""
from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from config import LOG_DIR, Settings
from src.date_resolver import resolve_capture_date
from src.duplicate_detector import build_destination_index
from src.filename_generator import build_filename, unique_path
from src.folder_watcher import FolderWatcher
from src.metadata_store import MetadataStore, make_snippet
from src.ocr_engine import TesseractNotAvailableError, check_tesseract, extract_text
from src.organizer import (
    ConfirmationRequiredError, FolderConfigError, PlannedItem,
    execute_plan, plan_screenshots, validate_folders,
)
from src.screenshot_detector import scan_folder, validate_manual_selection
from src.text_analyzer import analyze_text


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def configure_stdout() -> None:
    """Avoid Windows console crashes on unusual characters."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def collect_images(target: Path, settings: Settings) -> list[Path]:
    """A file -> itself; a folder -> its images (not recursive)."""
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(
            p for p in target.iterdir()
            if p.is_file() and p.suffix.lower() in settings.supported_extensions
        )
    return []


def confirm_move_prompt() -> bool:
    try:
        answer = input(
            "\nMoving removes each original AFTER a verified copy.\n"
            "Type MOVE to continue: "
        )
    except EOFError:
        return False
    return answer.strip() == "MOVE"


def cmd_check(settings: Settings) -> int:
    ok, message = check_tesseract(settings)
    print(message)
    return 0 if ok else 1


def cmd_ocr(path: Path, settings: Settings) -> int:
    if not path.is_file():
        print(f"File not found: {path}")
        return 2
    result = extract_text(path, settings)
    if result.error:
        print(f"[!] {result.error}")
        return 1
    print(f"Mean confidence: {result.mean_confidence:.1f}")
    print("----- OCR TEXT -----")
    print(result.full_text)
    return 0


def cmd_preview(target: Path, settings: Settings, show_candidates: bool) -> int:
    images = collect_images(target, settings)
    if not images:
        print(f"No supported images found at: {target}")
        return 2

    planned: set[str] = set()
    for path in images:
        print(f"\n=== {path.name}")
        if path.suffix.lower() not in settings.supported_extensions:
            print("  [skipped] unsupported file type")
            continue
        try:
            result = extract_text(path, settings)
            analysis = analyze_text(result, settings)
            date_info = resolve_capture_date(path)
        except OSError as exc:
            print(f"  [error] {exc}")
            logging.getLogger(__name__).warning("Preview failed for %s: %s", path, exc)
            continue

        filename = build_filename(analysis.title, date_info.value, path.suffix, settings)
        proposed = unique_path(path.parent, filename, planned)
        planned.add(proposed.name.lower())

        print(f"  Title source : {analysis.source} ({analysis.reason})")
        print(f"  Date         : {date_info.value} [{date_info.source}]")
        print(f"  Proposed name: {proposed.name}")
        if show_candidates:
            for cand in analysis.candidates[:5]:
                print(f"    candidate {cand.score:>5}: {cand.title}")
    print("\nPreview only. No files were changed.")
    return 0


def print_plan(items: list[PlannedItem]) -> None:
    for item in items:
        print(f"\n=== {item.original_name}")
        if item.status in ("skipped", "error"):
            print(f"  [{item.status}] {item.message}")
            continue
        print(f"  Category     : {item.category} ({item.category_reason})")
        print(f"  Title source : {item.title_source}")
        print(f"  Date         : {item.date_value} [{item.date_source}]")
        print(f"  Destination  : {item.destination}")
        if item.message:
            print(f"  Note         : {item.message}")


def print_results(items: list[PlannedItem]) -> None:
    print("\n----- RESULTS -----")
    for item in items:
        if item.new_name:
            line = f"{item.original_name} -> {item.category}/{item.new_name}"
        else:
            line = item.original_name
        note = f"  ({item.message})" if item.message else ""
        print(f"[{item.status.upper():7}] {line}{note}")
    counts = Counter(item.status for item in items)
    print("Summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def print_watch_result(item: PlannedItem) -> None:
    label = "DRY-RUN" if item.status == "planned" else item.status.upper()
    target = f"{item.category}/{item.new_name}" if item.new_name else "-"
    note = f"  ({item.message})" if item.message else ""
    print(f"[{label}] {item.original_name} -> {target}{note}", flush=True)


def cmd_organize(args: argparse.Namespace, settings: Settings) -> int:
    destination: Path = args.dest or settings.default_destination
    sources: list[Path] = []

    if not args.source and not args.files:
        print("Give --source <folder> and/or --files <image> [<image> ...]")
        return 2

    if args.files:
        valid, problems = validate_manual_selection(args.files, settings)
        for problem in problems:
            print(f"[warning] {problem}")
        sources.extend(valid)

    if args.source:
        try:
            validate_folders(args.source, destination)
            sources.extend(scan_folder(
                args.source, settings,
                recursive=args.recursive,
                require_pattern=not args.all_images,
                exclude_dirs=[destination],
            ))
        except (FolderConfigError, NotADirectoryError) as exc:
            print(f"[error] {exc}")
            return 2

    unique: dict[str, Path] = {}
    for path in sources:
        unique.setdefault(str(path.resolve()).lower(), path)
    sources = list(unique.values())

    if not sources:
        print("No screenshots found. Tip: use --all-images to ignore filename "
              "patterns, or --files to pick images by hand.")
        return 2

    store = MetadataStore(settings.database_path)
    index = build_destination_index(
        destination, settings.supported_extensions, cache=store.hash_cache()
    )
    items = plan_screenshots(sources, destination, settings, index=index)
    print_plan(items)

    if not args.apply:
        past = "copied" if args.mode == "copy" else "moved"
        print(f"\nDRY RUN: nothing was {past}. Add --apply to do it for real.")
        return 0

    confirmed = False
    if args.mode == "move":
        confirmed = confirm_move_prompt()
        if not confirmed:
            print("Cancelled. Nothing was changed.")
            return 1

    try:
        execute_plan(items, mode=args.mode, dry_run=False, confirm_move=confirmed)
    except ConfirmationRequiredError as exc:
        print(f"[error] {exc}")
        return 1
    print_results(items)

    try:
        saved = store.record_many(items)
        if saved:
            print(f"Saved {len(saved)} record(s) to {settings.database_path}")
    except sqlite3.Error as exc:
        print(f"[warning] Files were processed, but history could not be saved: {exc}")
        logging.getLogger(__name__).exception("Database write failed")
    return 0 if all(i.status != "error" for i in items) else 1


def cmd_watch(args: argparse.Namespace, settings: Settings) -> int:
    destination: Path = args.dest or settings.default_destination
    if not args.source.is_dir():
        print(f"[error] Source folder not found: {args.source}")
        return 2

    dry_run = not args.apply
    confirmed = False
    if args.apply and args.mode == "move":
        confirmed = confirm_move_prompt()
        if not confirmed:
            print("Cancelled. Nothing was changed.")
            return 1

    try:
        watcher = FolderWatcher(
            args.source, destination, settings,
            mode=args.mode, dry_run=dry_run, confirm_move=confirmed,
            require_pattern=not args.all_images,
            on_result=print_watch_result,
            store=MetadataStore(settings.database_path),
        )
    except (FolderConfigError, ConfirmationRequiredError) as exc:
        print(f"[error] {exc}")
        return 2

    try:
        watcher.start()
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        print(f"[error] Could not start watcher: {exc}")
        return 1
    state = "DRY RUN (nothing will be changed)" if dry_run else args.mode.upper()
    print(f"Watching {args.source}  ->  {destination}\nMode: {state}\nPress Ctrl+C to stop.")
    try:
        while watcher.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        watcher.stop()
    print("Watcher stopped.")
    return 0


def cmd_history(args: argparse.Namespace, settings: Settings) -> int:
    records = MetadataStore(settings.database_path).recent(args.limit)
    if not records:
        print("No history yet. Run 'organize --apply' or 'watch --apply' first.")
        return 0
    for rec in records:
        name = rec.new_name or rec.original_name
        print(f"#{rec.id:<4} {rec.processed_at}  {rec.status.upper():7}  "
              f"{rec.category or '-':14} {name}")
        if getattr(args, "details", False):
            print(f"  Original filename : {rec.original_name}")
            print(f"  Generated filename: {rec.new_name or '-'}")
            print(f"  Destination path  : {rec.destination_path or '-'}")
            print(f"  Extracted title   : {rec.title or '-'}")
            print(f"  Category          : {rec.category or '-'}")
            print(f"  Processing status : {rec.status}")
    return 0


def cmd_search(args: argparse.Namespace, settings: Settings) -> int:
    query = " ".join(args.query)
    records = MetadataStore(settings.database_path).search(
        query, category=args.category, limit=args.limit
    )
    if not records:
        print(f"No results for: {query}")
        return 0
    print(f"{len(records)} result(s) for: {query}")
    for rec in records:
        print(f"\n#{rec.id}  {rec.capture_date or '-'}  [{rec.category or '-'}]  "
              f"{rec.new_name or rec.original_name}")
        snippet = make_snippet(rec.ocr_text, args.query)
        if snippet:
            print(f"      {snippet}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Screenshot Organizer")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Verify that Tesseract is installed")

    ocr = sub.add_parser("ocr", help="Print OCR text for one image")
    ocr.add_argument("path", type=Path)

    prev = sub.add_parser("preview", help="Show proposed filenames (no changes)")
    prev.add_argument("path", type=Path, help="An image file or a folder of images")
    prev.add_argument("--show-candidates", action="store_true")

    org = sub.add_parser("organize", help="Rename + categorize (dry run by default)")
    org.add_argument("--source", type=Path, help="Folder to scan for screenshots")
    org.add_argument("--dest", type=Path, help="Destination folder (default: organized_screenshots)")
    org.add_argument("--files", type=Path, nargs="+", help="Hand-picked images (any filename)")
    org.add_argument("--recursive", action="store_true", help="Include subfolders of --source")
    org.add_argument("--all-images", action="store_true", help="Ignore filename patterns")
    org.add_argument("--mode", choices=("copy", "move"), default="copy")
    org.add_argument("--apply", action="store_true", help="Actually do it (default is a dry run)")

    watch = sub.add_parser("watch", help="Monitor a folder for NEW screenshots (Ctrl+C to stop)")
    watch.add_argument("--source", type=Path, required=True, help="Folder to monitor")
    watch.add_argument("--dest", type=Path, help="Destination folder (default: organized_screenshots)")
    watch.add_argument("--all-images", action="store_true", help="Ignore filename patterns")
    watch.add_argument("--mode", choices=("copy", "move"), default="copy")
    watch.add_argument("--apply", action="store_true", help="Actually copy/move (default is a dry run)")

    hist = sub.add_parser("history", help="Show recently processed screenshots")
    hist.add_argument("--limit", type=int, default=20)
    hist.add_argument("--details", action="store_true", help="Show saved filenames, destination, title, category and status")

    srch = sub.add_parser("search", help="Search OCR text, titles and filenames")
    srch.add_argument("query", nargs="+", help="Words to find (all must match)")
    srch.add_argument("--category", help="Only this category, e.g. Education")
    srch.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    setup_logging()
    args = build_parser().parse_args(argv)
    settings = Settings()
    try:
        if args.command == "check":
            return cmd_check(settings)
        if args.command == "ocr":
            return cmd_ocr(args.path, settings)
        if args.command == "preview":
            return cmd_preview(args.path, settings, args.show_candidates)
        if args.command == "watch":
            return cmd_watch(args, settings)
        if args.command == "history":
            return cmd_history(args, settings)
        if args.command == "search":
            return cmd_search(args, settings)
        return cmd_organize(args, settings)
    except TesseractNotAvailableError as exc:
        print(exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
