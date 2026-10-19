from dataclasses import replace
from types import SimpleNamespace

from config import Settings
from main import build_parser, cmd_history
from src.metadata_store import MetadataStore
from src.organizer import PlannedItem


def test_history_details_defaults_off():
    assert not build_parser().parse_args(["history"]).details
    assert build_parser().parse_args(["history", "--details"]).details


def test_history_details_uses_saved_fields_and_leaves_history_unchanged(tmp_path, capsys):
    settings = replace(Settings(), database_path=tmp_path / "db.sqlite")
    store = MetadataStore(settings.database_path)
    store.record(PlannedItem(source=tmp_path / "original.png", status="copied",
                             new_name="Huawei_Certification_2026-10-18.png",
                             destination=tmp_path / "Uncategorized" / "Huawei_Certification_2026-10-18.png",
                             title="Huawei Certification", category="Uncategorized"))
    before = store.recent()
    assert cmd_history(build_parser().parse_args(["history", "--details"]), settings) == 0
    output = capsys.readouterr().out
    for expected in ["Original filename : original.png", "Generated filename: Huawei_Certification_2026-10-18.png",
                     "Destination path", "Extracted title   : Huawei Certification",
                     "Category          : Uncategorized", "Processing status : copied"]:
        assert expected in output
    assert "reason" not in output.lower()
    assert store.recent() == before
    assert cmd_history(SimpleNamespace(limit=20), settings) == 0
    assert "Original filename" not in capsys.readouterr().out


def test_empty_history_details_does_not_create_database(tmp_path, capsys):
    settings = replace(Settings(), database_path=tmp_path / "data" / "db.sqlite")
    cmd_history(build_parser().parse_args(["history", "--details"]), settings)
    assert "No history yet" in capsys.readouterr().out
    assert not settings.database_path.parent.exists()
