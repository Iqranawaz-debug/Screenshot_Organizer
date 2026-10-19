from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
import sqlite3

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import config
from src import dashboard_data as data
from src.metadata_store import MetadataStore
from src.organizer import PlannedItem

APP = Path(__file__).resolve().parents[1] / 'app.py'


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    settings = replace(config.Settings(), database_path=tmp_path / 'data' / 'history.db')
    monkeypatch.setattr(config, 'Settings', lambda: settings)
    monkeypatch.setattr(config, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr('src.ocr_engine.check_tesseract', lambda settings: (True, 'OCR available'))
    monkeypatch.setattr('src.background_service.status', lambda runtime: {'active': False, 'state': 'stopped'})
    st.cache_data.clear()
    yield settings
    st.cache_data.clear()


def add_record(store, root, category='Education', title='Certificate of completion', status='copied'):
    store.record(PlannedItem(source=root / 'original.png', destination=root / 'missing.png',
                             new_name='Certificate_2026-10-18.png', title=title,
                             category=category, status=status, ocr_text='Private course completion text'))


def test_empty_database_metrics_do_not_create_files(tmp_path):
    path = tmp_path / 'missing' / 'history.db'
    assert data.metrics(path)['total'] == 0
    assert not path.parent.exists()


def test_actual_metrics_and_search(tmp_path):
    store = MetadataStore(tmp_path / 'db.sqlite')
    add_record(store, tmp_path)
    add_record(store, tmp_path, category='Uncategorized')
    add_record(store, tmp_path, status='error')
    values = data.metrics(store.db_path)
    assert (values['total'], values['today'], values['categorized'], values['uncategorized'], values['errors']) == (2, 2, 1, 1, 1)
    assert len(data.records(store, 'Private course', 'Education')) == 2
    assert len(data.records(store, category='Uncategorized')) == 1
    assert data.records(store, 'unmatched') == []


def test_preview_missing_and_malformed(tmp_path):
    assert data.preview(str(tmp_path / 'missing.png')) is None
    bad = tmp_path / 'bad.png'
    bad.write_text('not an image')
    assert data.preview(str(bad)) is None
    assert data.preview(None) is None
    assert data.preview(str(tmp_path / 'secret.txt')) is None


def test_invalid_configuration(tmp_path):
    (tmp_path / 'automation.json').write_text('{"source": 123}')
    config_value, error = data.configuration(tmp_path)
    assert config_value is None and error


def test_all_pages_are_independent_of_automation(workspace, monkeypatch):
    control = Mock(side_effect=AssertionError('Unexpected service mutation'))
    start = Mock(side_effect=AssertionError('Unexpected watcher thread'))
    monkeypatch.setattr(data, 'control', control)
    monkeypatch.setattr('src.folder_watcher.FolderWatcher.start', start)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    for page in ['Dashboard', 'Screenshot Gallery', 'Live Monitor', 'History & Search', 'Settings']:
        at.button(key=f'nav_{page}').click().run()
        assert not at.exception
    control.assert_not_called()
    start.assert_not_called()
    assert not workspace.database_path.exists()


@pytest.mark.parametrize('active', [False, True])
def test_monitor_actual_service_status(workspace, monkeypatch, active):
    monkeypatch.setattr('src.background_service.status', lambda runtime: {'active': active, 'state': 'running' if active else 'stopped', 'pid': 4321, 'mode': 'copy'})
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.button(key='nav_Live Monitor').click().run()
    assert not at.exception
    stop = next(b for b in at.button if b.label == 'Stop automation')
    assert stop.disabled is not active
    assert at.metric[0].value == ('Running' if active else 'Stopped')
    assert at.metric[1].value == ('4321' if active else '—')


def test_gallery_missing_file_and_history_search(workspace, tmp_path):
    store = MetadataStore(workspace.database_path)
    add_record(store, tmp_path)
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.button(key='nav_Screenshot Gallery').click().run()
    assert not at.exception
    assert any(b.label == 'View screenshot' for b in at.button)
    at.button(key='nav_History & Search').click().run()
    at.text_input[0].set_value('Private course').run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 1
    assert not at.text_area  # OCR stays hidden until explicitly revealed.
    at.text_input[0].set_value('unmatched').run()
    assert any('No history matches' in item.value for item in at.info)


def test_control_only_accepts_explicit_actions(tmp_path, monkeypatch):
    run = Mock(return_value=Mock(returncode=0, stdout='started', stderr=''))
    monkeypatch.setattr(data.subprocess, 'run', run)
    assert data.control(tmp_path, 'start') == (True, 'started')
    assert run.call_args.args[0][-1] == 'start'
    with pytest.raises(ValueError):
        data.control(tmp_path, 'configure')
    assert run.call_count == 1
