from dataclasses import replace
import pytest
from config import Settings
from src.models import OcrLine, OcrResult
from src.text_analyzer import category_interface_hint, content_text, analyze_text
from src.categorizer import categorize

SETTINGS = replace(Settings(), semantic_enabled=False, image_enabled=False)


def screen(*body):
    lines = [OcrLine('ChatGPT ~', 88, 15, 10, 13),
             OcrLine('Ask ChatGPT', 90, 20, 600, 824),
             OcrLine('University assignment Python invoice', 95, 20, 300, 20)]
    lines += [OcrLine(text, 95, 24, 200+i*30, 800) for i,text in enumerate(body)]
    return OcrResult(full_text='\n'.join(line.text for line in lines), lines=lines,
                     image_width=1800, image_height=900, mean_confidence=92)


def classify(result, settings=SETTINGS):
    return categorize(content_text(result), settings, interface_hint=category_interface_hint(result))


def test_chatgpt_home_uses_interface_without_sidebar_topics():
    result=screen("What's on your mind today?", 'Create an image or sticker', 'Write or edit', 'Search the web')
    assert category_interface_hint(result) == 'AI Chat'
    decision=classify(result)
    assert decision.category == 'AI Chat' and decision.method == 'interface'
    assert 'composer' in decision.reason
    assert 'University' not in content_text(result)
    assert analyze_text(result).title not in {'ChatGPT', 'Ask ChatGPT'}


@pytest.mark.parametrize('text,expected', [
    ('Python Exception Handling using try except blocks', 'Programming'),
    ('Huawei Certification has successfully completed the certification requirements', 'Education'),
])
def test_real_topic_takes_precedence(text,expected):
    assert classify(screen(text)).category == expected


@pytest.mark.parametrize('header,composer', [
    ('Article about ChatGPT','Ask ChatGPT'),
    ('ChatGPT','No composer here'),
    ('1_COPIED_ChatGPT','Ask ChatGPT'),
])
def test_mentions_and_history_do_not_establish_interface(header,composer):
    result=screen('An unrelated document')
    result.lines[0]=replace(result.lines[0],text=header)
    result.lines[1]=replace(result.lines[1],text=composer)
    assert category_interface_hint(result) is None


def test_uncertain_ocr_or_wrong_location_does_not_establish_interface():
    result=screen('Some content')
    result.lines[0]=replace(result.lines[0],confidence=20)
    assert category_interface_hint(result) is None
    result.lines[0]=replace(result.lines[0],confidence=90,left=800,top=400)
    assert category_interface_hint(result) is None


def test_disabled_ai_chat_category_is_respected():
    settings=replace(SETTINGS,categories={'Programming': {'python':3}})
    assert classify(screen('Welcome to this page'),settings).category == 'Uncategorized'
