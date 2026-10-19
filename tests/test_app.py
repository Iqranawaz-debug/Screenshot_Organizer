from pathlib import Path

from streamlit.testing.v1 import AppTest
import pytest
import streamlit as st
from dataclasses import replace
from unittest.mock import Mock

import config
from src.metadata_store import MetadataStore
from tests.test_services import PYTHON_OCR, make_png

# Retain all legacy manual-workspace regression coverage after the dashboard split.
APP = Path(__file__).resolve().parents[1] / "manual_app.py"


@pytest.fixture(autouse=True)
def isolated_app(tmp_path, monkeypatch):
    settings = replace(config.Settings(), database_path=tmp_path / "data" / "test.db",
                       default_destination=tmp_path / "out")
    monkeypatch.setattr(config, "Settings", lambda: settings)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("src.ocr_engine.check_tesseract", lambda settings: (True, "Test OCR ready"))
    st.cache_resource.clear()
    st.cache_data.clear()
    yield settings
    st.cache_resource.clear()
    st.cache_data.clear()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_first_load_has_no_processing_side_effects(isolated_app, monkeypatch):
    ocr = Mock(side_effect=AssertionError("Unexpected OCR"))
    start = Mock(side_effect=AssertionError("Unexpected watcher start"))
    monkeypatch.setattr("src.organizer.extract_text", ocr)
    monkeypatch.setattr("src.folder_watcher.FolderWatcher.start", start)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert not isolated_app.database_path.parent.exists()
    assert not isolated_app.default_destination.exists()
    ocr.assert_not_called()
    start.assert_not_called()
    assert button(at, "Stop watcher").disabled
    assert next(c for c in at.checkbox if c.label.startswith("Dry run")).value


def test_preview_apply_copies_and_reports_success(tmp_path, isolated_app, monkeypatch):
    shot = make_png(tmp_path / "sample_images" / "Screenshot (1).png")
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: PYTHON_OCR)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    button(at, "Scan & preview").click().run()
    assert not at.exception
    assert not isolated_app.default_destination.exists()
    assert not isolated_app.database_path.parent.exists()
    button(at, "Apply approved items").click().run()
    assert not at.exception
    assert shot.exists()
    assert len(list(isolated_app.default_destination.rglob("*.png"))) == 1
    assert any("Copied 1" in s.value for s in at.success)
    assert MetadataStore(isolated_app.database_path).count() == 1
    assert at.session_state["plan_items"] is None
    at.run()
    assert any("Copied 1" in s.value for s in at.success)


def test_move_requires_exact_confirmation(tmp_path, isolated_app, monkeypatch):
    shot = make_png(tmp_path / "sample_images" / "Screenshot (1).png")
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: PYTHON_OCR)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    button(at, "Scan & preview").click().run()
    next(c for c in at.checkbox if c.label.startswith("Move instead")).check().run()
    assert button(at, "Apply approved items").disabled
    confirmation = next(t for t in at.text_input if t.label == "Type MOVE to confirm")
    confirmation.set_value("MOVE ").run()
    assert button(at, "Apply approved items").disabled
    confirmation.set_value("MOVE").run()
    assert not button(at, "Apply approved items").disabled
    assert shot.exists()
    assert not isolated_app.default_destination.exists()


def test_database_errors_show_warning(isolated_app, monkeypatch):
    import sqlite3
    monkeypatch.setattr(MetadataStore, "recent", Mock(side_effect=sqlite3.OperationalError("locked")))
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert any("History unavailable: locked" in w.value for w in at.warning)


def test_app_loads_without_exceptions():
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert len(at.tabs) == 3
