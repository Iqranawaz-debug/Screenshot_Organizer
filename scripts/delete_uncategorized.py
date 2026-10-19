"""Delete every screenshot filed as Uncategorized: the organized copies AND their history rows.

Safe by default:
  * dry run unless you pass --apply
  * copy mode only: records whose original was removed (status 'moved') are never touched
  * only files inside the destination folder are ever deleted
  * files go to the Recycle Bin (pip install send2trash) unless you pass --permanent
  * the database is backed up before any row is removed
  * refuses to run while the background service is active

Usage (from the project root, with the monitor STOPPED):
    python scripts/delete_uncategorized.py            # preview only
    python scripts/delete_uncategorized.py --apply    # really delete
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PROJECT_ROOT, Settings
from src import dashboard_data as data
from src.background_service import status


def to_trash(path: Path, permanent: bool) -> None:
    if permanent:
        path.unlink()
        return
    from send2trash import send2trash
    send2trash(str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually delete (default is a preview)")
    parser.add_argument("--permanent", action="store_true", help="skip the Recycle Bin")
    args = parser.parse_args()

    settings = Settings()
    config, error = data.configuration(PROJECT_ROOT)
    destination = Path(config.destination if config else settings.default_destination).resolve()
    database = Path(config.database if config else settings.database_path)
    name = settings.uncategorized_name

    if not database.exists():
        print(f"No history database at {database}")
        return 1
    if args.apply and status(PROJECT_ROOT / "runtime").get("active"):
        print("The background service is running. Click 'Stop monitor' in the dashboard first, then re-run.")
        return 1
    if args.apply and not args.permanent:
        try:
            import send2trash  # noqa: F401
        except ImportError:
            print("Recycle Bin support is missing. Run: pip install send2trash   (or use --permanent)")
            return 1

    db = sqlite3.connect(database, timeout=5)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT id, new_name, destination_path, status FROM screenshots "
        "WHERE (category IS NULL OR category = '' OR category = ?)", (name,)).fetchall()
    copied = [r for r in rows if r["status"] == "copied"]
    skipped_moved = [r for r in rows if r["status"] == "moved"]
    print(f"Destination: {destination}")
    print(f"Uncategorized records: {len(rows)}  (copied: {len(copied)}, moved/kept untouched: {len(skipped_moved)}, other: {len(rows) - len(copied) - len(skipped_moved)})")

    files, outside, missing_ids = [], [], []
    for r in copied:
        path = Path(r["destination_path"]) if r["destination_path"] else None
        if path is None or not path.exists():
            missing_ids.append(r["id"])
        elif path.resolve().is_relative_to(destination):
            files.append((r["id"], path))
        else:
            outside.append(path)
    print(f"Files to delete: {len(files)}   already missing on disk: {len(missing_ids)}   outside destination (skipped): {len(outside)}")
    for _, path in files[:8]:
        print(f"   {path.name}")
    if len(files) > 8:
        print(f"   ... and {len(files) - 8} more")

    if not args.apply:
        print("\nPreview only. Nothing was changed. Re-run with --apply to delete.")
        return 0
    if not copied:
        print("Nothing to delete.")
        return 0

    backup = database.with_name(f"{database.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}{database.suffix}")
    shutil.copy2(database, backup)
    print(f"\nDatabase backed up to {backup}")

    deleted, failed = 0, []
    for rec_id, path in files:
        try:
            to_trash(path, args.permanent)
            deleted += 1
        except OSError as exc:
            failed.append((rec_id, path, exc))
    failed_ids = {rec_id for rec_id, _, _ in failed}
    # Rows are removed only for files we deleted or that were already gone; never for skipped/failed ones.
    ids = [rec_id for rec_id, _ in files if rec_id not in failed_ids] + missing_ids
    db.executemany("DELETE FROM screenshots WHERE id = ?", [(i,) for i in ids])
    db.commit()
    db.close()

    folder = destination / name
    if folder.is_dir() and not any(folder.iterdir()):
        folder.rmdir()
    print(f"Deleted {deleted} file(s) and {len(ids)} history record(s).")
    for rec_id, path, exc in failed:
        print(f"   FAILED (record kept): {path.name}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())