from datetime import date
from pathlib import Path

from src.metadata_store import MetadataStore, make_snippet
from src.organizer import PlannedItem


def make_item(
    tmp_path: Path,
    name: str = "Python_Exception_Handling_2026-10-17.png",
    *,
    status: str = "copied",
    text: str = "Python Exception Handling try except",
    category: str = "Programming",
    file_hash: str = "abc123",
) -> PlannedItem:
    dest = tmp_path / "out" / category / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"data")  # 4 bytes
    return PlannedItem(
        source=tmp_path / "src" / "Screenshot (1).png",
        status=status,
        new_name=name,
        title="Heading",
        title_source="heading",
        date_value=date(2026, 10, 17),
        date_source="file_modified",
        category=category,
        destination=dest,
        ocr_text=text,
        file_hash=file_hash,
    )


def test_record_and_recent(tmp_path):
    store = MetadataStore(tmp_path / "db" / "t.db")
    assert store.record(make_item(tmp_path)) == 1

    [rec] = store.recent(10)
    assert rec.original_name == "Screenshot (1).png"
    assert rec.new_name == "Python_Exception_Handling_2026-10-17.png"
    assert rec.capture_date == "2026-10-17" and rec.date_source == "file_modified"
    assert rec.status == "copied" and rec.category == "Programming"
    assert "Exception" in rec.ocr_text


def test_only_real_outcomes_are_recorded(tmp_path):
    db = tmp_path / "t.db"
    store = MetadataStore(db)
    assert store.record(make_item(tmp_path, status="skipped")) is None
    assert store.record(make_item(tmp_path, status="planned")) is None
    assert store.count() == 0
    assert not db.exists()  # nothing was written, so no file was created


def test_reading_a_missing_database_creates_nothing(tmp_path):
    db = tmp_path / "data" / "missing.db"
    store = MetadataStore(db)
    assert store.recent() == []
    assert store.search("anything") == []
    assert store.hash_cache() == {}
    assert store.count() == 0
    assert not db.exists() and not db.parent.exists()


def test_search_requires_all_words_case_insensitively(tmp_path):
    store = MetadataStore(tmp_path / "t.db")
    store.record(make_item(tmp_path, "Python_2026-10-17.png",
                           text="Python Exception Handling", category="Programming",
                           file_hash="h1"))
    store.record(make_item(tmp_path, "Databases_2026-10-17.png",
                           text="Database Management Assignment 02", category="Education",
                           file_hash="h2"))

    assert len(store.search("EXCEPTION")) == 1
    assert len(store.search("python handling")) == 1
    assert store.search("python assignment") == []
    assert store.search("zzz") == []
    assert store.search("   ") == []
    assert [r.category for r in store.search("assignment", category="Education")] == ["Education"]
    assert store.search("assignment", category="Programming") == []


def test_percent_sign_is_searched_literally(tmp_path):
    store = MetadataStore(tmp_path / "t.db")
    store.record(make_item(tmp_path, "A_2026-10-17.png", text="Progress 100% done", file_hash="h1"))
    store.record(make_item(tmp_path, "B_2026-10-17.png", text="Nothing special", file_hash="h2"))
    assert [r.new_name for r in store.search("%")] == ["A_2026-10-17.png"]


def test_hash_cache_holds_size_mtime_and_hash(tmp_path):
    store = MetadataStore(tmp_path / "t.db")
    item = make_item(tmp_path, file_hash="deadbeef")
    store.record(item)
    store.record(make_item(tmp_path, "Bad_2026-10-17.png", status="error", file_hash="ffff"))

    cache = store.hash_cache()
    key = str(item.destination.resolve())
    assert cache[key][0] == 4 and cache[key][2] == "deadbeef"
    assert all(entry[2] != "ffff" for entry in cache.values())


def test_make_snippet_centres_on_the_match():
    text = "alpha beta\ngamma delta epsilon zeta eta theta"
    snippet = make_snippet(text, ["gamma"], width=20)
    assert "gamma" in snippet and "\n" not in snippet
    assert make_snippet(None, ["x"]) == ""
    assert make_snippet("short text", ["nothing"]).startswith("short text")
