"""Local dashboard for previewing and approving screenshot organization."""
from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

import streamlit as st

from config import PROJECT_ROOT, Settings
from src.metadata_store import MetadataStore, make_snippet
from src.background_service import configure as configure_automation, status as automation_status
from src.ocr_engine import (
    TESSERACT_INSTALL_HELP, TesseractNotAvailableError, check_tesseract,
)
from src.organizer import ConfirmationRequiredError, FolderConfigError, PlannedItem
from src.services import (
    ApplyOutcome, WatcherController, apply_approved, build_plan, parse_path_lines,
)

settings = Settings()
store = MetadataStore(settings.database_path)


@st.cache_resource
def get_watcher_controller() -> WatcherController:
    return WatcherController(settings, store)


@st.cache_data(ttl=60)
def tesseract_status() -> tuple[bool, str]:
    return check_tesseract(settings)


def item_rows(items: list[PlannedItem]) -> list[dict[str, object]]:
    return [{
        "Original": i.original_name, "Proposed name": i.new_name,
        "Category": i.category, "Title source": i.title_source,
        "Date": str(i.date_value or ""), "Date source": i.date_source,
        "Status": i.status, "Note": i.message,
    } for i in items]


def show_outcome(outcome: ApplyOutcome) -> None:
    counts = Counter(i.status for i in outcome.items)
    for column, status in zip(st.columns(4), ("copied", "moved", "skipped", "error")):
        column.metric(status.title(), counts[status])
    if counts["copied"] or counts["moved"]:
        st.success(f"Copied {counts['copied']} and moved {counts['moved']} screenshot(s).")
    for item in outcome.items:
        if item.status == "error":
            st.error(f"{item.original_name}: {item.message}")
    if outcome.history_error:
        st.warning(f"Files were processed, but history could not be saved: {outcome.history_error}")
    st.dataframe(item_rows(outcome.items), hide_index=True)


def inspect_item(items: list[PlannedItem]) -> None:
    position = st.selectbox("Inspect a screenshot", range(len(items)),
                            format_func=lambda i: items[i].original_name)
    item = items[position]
    left, right = st.columns(2)
    with left:
        try:
            st.image(item.source.read_bytes(), caption=item.original_name)
        except (OSError, ValueError) as exc:
            st.warning(f"Image preview unavailable: {exc}")
    with right:
        st.text_area("Full OCR text", item.ocr_text, disabled=True, height=240)
        st.write(f"Category reason: {item.category_reason or 'Not available'}")
        st.write(f"Title reason: {item.title_reason or 'Not available'}")


def organize_tab(source: Path | None, destination: Path | None,
                 extras: list[Path], all_images: bool, recursive: bool) -> None:
    if st.button("Scan & preview"):
        st.session_state.plan_items = None
        st.session_state.plan_warnings = []
        st.session_state.last_outcome = None
        if destination is None:
            st.warning("Enter a destination folder.")
        elif source is None and not extras:
            st.warning("Enter a source folder or extra image paths.")
        else:
            try:
                with st.spinner("Reading screenshots with OCR..."):
                    items, warnings = build_plan(
                        source, destination, settings, extra_files=extras,
                        include_all_images=all_images, recursive=recursive, store=store,
                    )
                st.session_state.plan_items = items
                st.session_state.plan_warnings = warnings
                st.session_state.plan_destination = destination
                st.session_state.plan_version = st.session_state.get("plan_version", 0) + 1
            except TesseractNotAvailableError:
                st.error(TESSERACT_INSTALL_HELP)
            except FolderConfigError as exc:
                st.error(str(exc))
            except NotADirectoryError as exc:
                st.error(str(exc))
            except (sqlite3.Error, OSError, ValueError) as exc:
                st.warning(str(exc))

    for warning in st.session_state.get("plan_warnings", []):
        st.warning(warning)
    items = st.session_state.get("plan_items")
    if items is not None:
        counts = Counter(i.status for i in items)
        st.write(f"Planned: {counts['planned']} | Skipped: {counts['skipped']} | Errors: {counts['error']}")
        st.caption(f"Preview destination: {st.session_state.plan_destination}")
        if not items:
            st.info("No screenshots found. Try including all images or adding extra paths.")
        else:
            rows = [{"Approve": i.status == "planned", **row}
                    for i, row in zip(items, item_rows(items))]
            edited = st.data_editor(
                rows, hide_index=True, disabled=list(item_rows(items)[0]),
                column_config={"Approve": st.column_config.CheckboxColumn("Approve")},
                key=f"approval_{st.session_state.plan_version}",
            )
            approved = [i for i, row in enumerate(edited)
                        if row["Approve"] and items[i].status == "planned"]
            inspect_item(items)
            move = st.checkbox("Move instead of copy (removes originals after a verified copy)")
            confirmation = st.text_input("Type MOVE to confirm") if move else ""
            st.caption("Nothing is copied until you click Apply")
            if st.button("Apply approved items", disabled=not approved or (move and confirmation != "MOVE")):
                try:
                    outcome = apply_approved(
                        items, approved, st.session_state.plan_destination, settings,
                        mode="move" if move else "copy",
                        confirm_move=move and confirmation == "MOVE", store=store,
                    )
                    st.session_state.last_outcome = outcome
                    st.session_state.plan_items = None
                    st.session_state.plan_warnings = []
                    st.rerun()
                except ConfirmationRequiredError as exc:
                    st.error(str(exc))
                except (sqlite3.Error, OSError, ValueError) as exc:
                    st.warning(str(exc))
    outcome = st.session_state.get("last_outcome")
    if outcome is not None:
        show_outcome(outcome)


def watcher_results(controller: WatcherController) -> None:
    st.write("Running" if controller.is_running else "Stopped")
    if controller.source is not None:
        st.caption(f"{controller.source} → {controller.destination} | "
                   f"{'Dry run' if controller.dry_run else 'Copy'}")
    results = controller.recent_results()
    if results:
        st.dataframe(item_rows(results), hide_index=True)
    else:
        st.info("No watcher results yet.")


if hasattr(st, "fragment"):
    watcher_results = st.fragment(run_every=2)(watcher_results)


def watcher_tab(source: Path | None, destination: Path | None, all_images: bool) -> None:
    with st.expander("Background automation (independent of this dashboard)", expanded=True):
        try:
            automation = automation_status()
            st.write(f"Background automation: {automation.get('state', 'stopped')}")
            if automation.get("active"):
                st.caption(f"{automation.get('source', '')} → {automation.get('destination', '')} | Copy only")
            if automation.get("error"):
                st.warning(automation["error"])
            st.caption("Use scripts/Start-Automation.ps1 and Stop-Automation.ps1 to control the background process. "
                       "Logs: runtime/automation.log. Closing this dashboard does not stop it.")
            st.button("Refresh automation status")
            if st.button("Save sidebar folders for background automation", disabled=automation.get("active", False)):
                if source is None or destination is None:
                    st.warning("Enter both folders first, then save. Stop automation before changing configuration.")
                else:
                    configure_automation(source, destination)
                    st.success("Saved. Start background automation to use these folders. Originals will be retained.")
        except (OSError, ValueError) as exc:
            st.warning(str(exc))
    controller = get_watcher_controller()
    st.caption("The controls below are an optional dashboard watcher. A source can have only one watcher.")
    st.write("Watches only the chosen source folder for NEW screenshots. Copy mode only.")
    dry_run = st.checkbox("Dry run (preview only, recommended)", value=True)
    if not dry_run:
        st.warning("New screenshots will be copied after you start the watcher.")
    if st.button("Start watcher", disabled=controller.is_running):
        if source is None or destination is None:
            st.warning("Enter both source and destination folders.")
        else:
            try:
                controller.start(source, destination, dry_run=dry_run, include_all_images=all_images)
                st.rerun()
            except (FolderConfigError, NotADirectoryError, RuntimeError) as exc:
                st.error(str(exc))
            except (sqlite3.Error, OSError, ValueError) as exc:
                st.warning(str(exc))
    if st.button("Stop watcher", disabled=not controller.is_running):
        controller.stop()
        st.rerun()
    if not hasattr(st, "fragment"):
        st.button("Refresh")
    watcher_results(controller)


def history_tab() -> None:
    query = st.text_input("Search OCR text, titles and filenames", help="All words must match.")
    category = st.selectbox("Category", ["All", *settings.categories, settings.uncategorized_name])
    try:
        records = (store.search(query, category=None if category == "All" else category, limit=50)
                   if query.strip() else store.recent(50))
        if not records:
            st.info("No results for this search." if query.strip()
                    else "No history yet. Approve and apply a preview first.")
            return
        st.dataframe([{
            "id": r.id, "processed": r.processed_at, "status": r.status,
            "category": r.category, "new name": r.new_name, "date": r.capture_date,
            "snippet": make_snippet(r.ocr_text, query.split()),
        } for r in records], hide_index=True)
        index = st.selectbox("Inspect history record", range(len(records)),
                             format_func=lambda i: f"#{records[i].id} {records[i].new_name or records[i].original_name}")
        record = records[index]
        st.text_area("Recorded OCR text", record.ocr_text or "", disabled=True, height=240)
        st.text(f"Source: {record.source_path}\nDestination: {record.destination_path or '-'}")
    except (sqlite3.Error, OSError) as exc:
        st.warning(f"History unavailable: {exc}")


def main() -> None:
    st.set_page_config(page_title="Smart Screenshot Organizer", layout="wide")
    st.title("Smart Screenshot Organizer")
    with st.sidebar:
        st.title("Screenshot Organizer")
        st.write("Preview, approve and find your screenshots.")
        ok, message = tesseract_status()
        if ok:
            st.success(message)
        else:
            st.error(message)
            with st.expander("Tesseract installation help"):
                st.text(TESSERACT_INSTALL_HELP)
        source_text = st.text_input("Source folder", str(PROJECT_ROOT / "sample_images"))
        destination_text = st.text_input("Destination folder", str(settings.default_destination))
        all_images = st.checkbox("Include all images (ignore screenshot filename patterns)")
        recursive = st.checkbox("Include subfolders")
        extras = parse_path_lines(st.text_area("Extra image paths (one per line, any filename)"))
        st.caption("Nothing is copied until you approve it.")
    source = Path(source_text.strip()) if source_text.strip() else None
    destination = Path(destination_text.strip()) if destination_text.strip() else None
    organize, watcher, history = st.tabs(["Organize", "Watcher", "History & Search"])
    with organize:
        organize_tab(source, destination, extras, all_images, recursive)
    with watcher:
        watcher_tab(source, destination, all_images)
    with history:
        history_tab()


if __name__ == "__main__":
    main()
