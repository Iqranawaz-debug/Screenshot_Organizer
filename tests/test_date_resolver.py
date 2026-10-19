import os
from datetime import datetime

from PIL import Image

from src.date_resolver import resolve_capture_date


def test_falls_back_to_file_modified_date(tmp_path):
    path = tmp_path / "shot.png"
    Image.new("RGB", (10, 10), "white").save(path)
    stamp = datetime(2026, 10, 17, 12, 0, 0).timestamp()
    os.utime(path, (stamp, stamp))

    info = resolve_capture_date(path)
    assert info.source == "file_modified"
    assert info.value.isoformat() == "2026-10-17"