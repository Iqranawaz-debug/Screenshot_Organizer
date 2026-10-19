from pathlib import Path

import pytest
from PIL import Image

from config import Settings
from src.categorizer import categorize
from src.content_filter import meaningful_line
from src.metadata_store import MetadataStore
from src.models import OcrLine, OcrResult
from src.organizer import execute_plan, plan_screenshots
from src.text_analyzer import analyze_text, content_text


def ocr(*texts):
    return OcrResult(full_text='\n'.join(texts),
                     lines=[OcrLine(text, 95, 20, 40 + i * 35, 300) for i, text in enumerate(texts)],
                     mean_confidence=95, image_height=900)


@pytest.mark.parametrize('text', [
    '#4 2026-10-18T15:21:35+00:00 COPIED Education Huawei_Certification_2026-10-18.png',
    '1_COPIED_Uncategorized_ChatGPT_Q',
    'Huawei_Certification_2026-10-18.png',
    'Course_Completion_2026-10-18',
    r'C:\Users\Example\Education\Course_Completion.png',
    'Original filename: Python_course.png',
    'Extracted title: Certificate of completion',
    'Processing status: copied',
    'ID Date Status Category Filename',
    '2026-10-18 12:00:00 INFO copied certificate of completion',
    'DEBUG: python course certification',
    r'(.venv) PS C:\Project>',
])
def test_administrative_lines_are_not_evidence(text):
    result = ocr(text)
    assert meaningful_line(text) is None
    assert analyze_text(result).title is None
    assert categorize(content_text(result), Settings()).category == 'Uncategorized'
    assert categorize(text, Settings()).category == 'Uncategorized'
    assert result.full_text == text


def test_terminal_history_keeps_command_without_borrowing_category():
    result = ocr(r'(.venv) PS C:\Education> .\.venv\Scripts\python.exe main.py history',
                 '#4 COPIED Education Certificate_of_Completion_2026-10-18.png',
                 '#3 COPIED Programming Python_exception_2026-10-18.png')
    assert analyze_text(result).title == 'python main.py history'
    # The current rules recognize Python plus a .py command as Programming.
    decision = categorize(content_text(result), Settings())
    assert decision.category == 'Programming'
    assert 'certificate of completion' not in decision.matched


def test_terminal_error_remains_useful():
    result = ocr(r'PS C:\Project> python app.py', "ModuleNotFoundError: No module named flask")
    assert 'ModuleNotFoundError' in [c.title.split()[0] for c in analyze_text(result).candidates]
    assert 'No module named flask' in content_text(result)


def test_quoted_history_filename_loses_to_actual_heading():
    result = ocr('1_COPIED_Uncategorized_ChatGPT_Q',
                 '2. Why is screenshot #5 named so strangely?', 'history as the filename.',
                 'Verify the classifier using a screenshot with course or certification information.')
    assert analyze_text(result).title == 'Why is screenshot 5 named'
    assert categorize(content_text(result), Settings()).category == 'Uncategorized'


@pytest.mark.parametrize('texts, category', [
    (['Huawei Certification', 'has successfully completed the Huawei certification requirements'], 'Education'),
    (['Cisco Cybersecurity', 'Certificate of Completion'], 'Education'),
    (['Python Exception Handling', 'Use try and except blocks'], 'Programming'),
    (['python javascript assignment lecture'], 'Uncategorized'),
])
def test_meaningful_content_survives(texts, category):
    result = ocr(*texts)
    assert analyze_text(result).title is not None
    assert categorize(content_text(result), Settings()).category == category


def test_copy_and_history_preserve_full_ocr_when_title_falls_back(tmp_path, monkeypatch):
    text = '#4 COPIED Education Certificate_of_Completion_2026-10-18.png'
    monkeypatch.setattr('src.organizer.extract_text', lambda path, settings: ocr(text))
    source = tmp_path / 'source.png'
    Image.new('RGB', (20, 20), 'white').save(source)
    [item] = plan_screenshots([source], tmp_path / 'out', Settings())
    assert item.title is None
    assert item.new_name.startswith('Screenshot_')
    assert item.category == 'Uncategorized'
    execute_plan([item], dry_run=False)
    store = MetadataStore(tmp_path / 'history.db')
    store.record(item)
    assert store.recent()[0].ocr_text == text
    assert source.exists()
    assert plan_screenshots([source], tmp_path / 'out', Settings())[0].status == 'skipped'
