"""Detect identical files by content hash (not by name)."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes, read in chunks (safe for large files)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HashIndex:
    """Remembers the first path seen for each content hash."""

    def __init__(self) -> None:
        self._by_hash: dict[str, Path] = {}

    def add(self, digest: str, path: Path) -> None:
        self._by_hash.setdefault(digest, path)

    def find(self, digest: str) -> Path | None:
        return self._by_hash.get(digest)
    
    def discard(self, digest: str) -> None:
        self._by_hash.pop(digest, None)

    def __len__(self) -> int:
        return len(self._by_hash)


def build_destination_index(
    destination: Path,
    extensions: Iterable[str],
    cache: dict[str, tuple[int, int, str]] | None = None,
) -> HashIndex:
    """Hash every supported image already inside the destination folder.

    `cache` maps str(resolved path) -> (size, mtime_ns, sha256). A cached hash is
    reused only if the file's size and modified time are unchanged.
    """
    index = HashIndex()
    if not destination.is_dir():
        return index
    allowed = {ext.lower() for ext in extensions}
    for path in destination.rglob("*"):
        try:
            if not (path.is_file() and path.suffix.lower() in allowed):
                continue
            digest: str | None = None
            if cache:
                stat = path.stat()
                cached = cache.get(str(path.resolve()))
                if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
                    digest = cached[2]
            if digest is None:
                digest = file_sha256(path)
            index.add(digest, path)
        except OSError as exc:
            logger.warning("Could not hash %s: %s", path, exc)
    return index
