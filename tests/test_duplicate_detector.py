from src.duplicate_detector import build_destination_index, file_sha256


def test_same_bytes_give_same_hash(tmp_path):
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    a.write_bytes(b"abc")
    b.write_bytes(b"abc")
    c.write_bytes(b"abd")
    assert file_sha256(a) == file_sha256(b) != file_sha256(c)


def test_index_finds_existing_destination_files(tmp_path):
    existing = tmp_path / "Education" / "x.png"
    existing.parent.mkdir()
    existing.write_bytes(b"content")

    index = build_destination_index(tmp_path, (".png",))
    assert index.find(file_sha256(existing)) == existing
    assert len(build_destination_index(tmp_path / "missing", (".png",))) == 0


def test_cache_skips_rehashing_unchanged_files(tmp_path):
    existing = tmp_path / "x.png"
    existing.write_bytes(b"content")
    stat = existing.stat()
    cache = {str(existing.resolve()): (stat.st_size, stat.st_mtime_ns, "cachedhash")}

    index = build_destination_index(tmp_path, (".png",), cache=cache)
    assert index.find("cachedhash") == existing          # cached hash was used
    assert index.find(file_sha256(existing)) is None     # real hash was NOT computed
