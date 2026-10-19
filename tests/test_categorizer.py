from config import Settings
from src.categorizer import categorize
import pytest

SETTINGS = Settings()


def test_programming_text():
    text = "Python Exception Handling using except blocks def divide print result"
    assert categorize(text, SETTINGS).category == "Programming"


def test_education_text_beats_programming_words():
    text = ("Database Management Systems Assignment 02 Submit the ER diagram "
            "before the deadline Normalize the schema")
    assert categorize(text, SETTINGS).category == "Education"


def test_weak_evidence_is_uncategorized():
    assert categorize("Hello world nothing special", SETTINGS).category == "Uncategorized"


def test_empty_text_is_uncategorized():
    assert categorize("", SETTINGS).category == "Uncategorized"


@pytest.mark.parametrize("text, expected", [
    ("Huawei Certification\nhas successfully completed the Huawei certification requirements "
     "and is recognized as a\nDatacom\nValid Through May 19, 2028", "Education"),
    ("Cisco Cybersecurity\nCertificate of Completion\nSuccessfully completed an online course", "Education"),
    ("University assignment\nSubmit your academic assignment before the deadline", "Education"),
    ("Python programming tutorial\nFunctions and exception handling with try except", "Programming"),
    ("Windows Settings\nDisplay brightness\nChoose your background", "System & Files"),
    ("Client invoice\nMeeting report about the supplier insurance certificate", "Work"),
    ("Certificate", "Uncategorized"),
    ("Certification", "Uncategorized"),
    ("Successfully completed the invoice payment", "Uncategorized"),
    ("Python SSL certificate error", "Programming"),
])
def test_educational_and_noneducational_contexts(text, expected):
    assert categorize(text, SETTINGS).category == expected


@pytest.mark.parametrize("phrase", [
    "certificate of completion", "completed a course", "training program",
    "professional certification", "online course", "examination",
    "academic assignment", "course completion",
])
def test_strong_educational_phrases(phrase):
    assert categorize(phrase, SETTINGS).category == "Education"


def test_certificate_metadata_does_not_add_evidence():
    text = ("Certificate No. COURSE-EXAM-PYTHON-123\n"
            "Validation URL: https://example.invalid/online-course/assignment\n"
            "Recipient: Python University\nValid Through May 19, 2028")
    result = categorize(text, SETTINGS)
    assert result.category == "Uncategorized" and result.score == 0


def test_completion_context_not_overridden_by_recipient_or_validation():
    text = ("Huawei Certification\nSuccessfully completed\nRecipient:\n"
            "Python Javascript\nCertificate No. API-JSON-123\n"
            "https://example.invalid/invoice/meeting/project\nValid Through May 19, 2028")
    result = categorize(text, SETTINGS)
    assert result.category == "Education"
    assert set(result.matched) == {"certification", "successfully completed"}


def test_phrase_normalization_and_conservative_tie():
    assert categorize("CERTIFICATE OF\nCOMPLETION", SETTINGS).category == "Education"
    assert categorize("Training-program", SETTINGS).category == "Education"
    assert categorize("Examination\ninvoice client", SETTINGS).category == "Uncategorized"
