"""S1: fetch the NCEI Storm Events bulk files with a cached, checksummed snapshot and a manifest.

Follows crc-sdk's ``IBTrACSPlan`` pattern: the plan names remote files, ``explain()`` does no I/O,
``prefetch()`` downloads what is missing (or verifies the cache in ``offline`` mode) and records
SHA-256, size, HTTP headers and retrieval time per file in ``manifest.json``. NCEI re-creates each
yearly file in place (the ``c`` date in the name), so the manifest is what pins a snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
FILE_TYPES = ("details", "locations", "fatalities")
TERMS_URL = "https://www.ncei.noaa.gov/access/storm-events-database/"
CITATION = (
    "NOAA National Centers for Environmental Information, Storm Events Database, "
    "bulk CSV files (details, locations, fatalities)"
)
_NAME = re.compile(
    r"StormEvents_(details|locations|fatalities)-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz"
)
_USER_AGENT = "crc-lab/0.0.1 (+https://github.com/shlyakh/crc-lab)"


@dataclass(frozen=True)
class RemoteFile:
    file_type: str
    year: int
    created: str  # yyyymmdd from the file name
    name: str

    @property
    def url(self) -> str:
        return ROOT + self.name


def http_request(url: str) -> Request:
    return Request(url, headers={"User-Agent": _USER_AGENT})


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def parse_listing(html: str) -> list[RemoteFile]:
    """The newest creation date per (type, year) from the directory index."""
    found: dict[tuple[str, int], RemoteFile] = {}
    for match in _NAME.finditer(html):
        file_type, year, created = match.group(1), int(match.group(2)), match.group(3)
        candidate = RemoteFile(file_type, year, created, match.group(0))
        current = found.get((file_type, year))
        if current is None or created > current.created:
            found[(file_type, year)] = candidate
    return sorted(found.values(), key=lambda f: (f.file_type, f.year))


@dataclass(frozen=True)
class StormEventsPlan:
    """Which yearly NCEI files to hold, where, and how strictly."""

    cache_dir: Path
    mode: str = "reuse"
    years: tuple[int, int] | None = None
    file_types: tuple[str, ...] = FILE_TYPES

    def __post_init__(self) -> None:
        if self.mode not in {"reuse", "offline", "refresh"}:
            raise ValueError("mode must be reuse, offline or refresh")
        if any(t not in FILE_TYPES for t in self.file_types):
            raise ValueError(f"file_types must be among {FILE_TYPES}")

    def between(self, start: int, end: int) -> StormEventsPlan:
        if start > end or start < 1950:
            raise ValueError("years must be ordered and not before 1950")
        return replace(self, years=(start, end))

    def only(self, *file_types: str) -> StormEventsPlan:
        return replace(self, file_types=tuple(file_types))

    @property
    def directory(self) -> Path:
        return self.cache_dir / "storm-events" / "ncei"

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    def explain(self) -> dict[str, Any]:
        return {
            "root": ROOT,
            "file_types": list(self.file_types),
            "years": self.years,
            "cache_dir": str(self.directory),
            "mode": self.mode,
            "selection": "newest creation date per year and file type, from the directory listing",
            "terms_url": TERMS_URL,
            "citation": CITATION,
        }

    def read_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return {"files": {}}

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump(manifest, handle, indent=1, sort_keys=True)
        os.chmod(tmp, 0o644)
        os.replace(tmp, self.manifest_path)

    def _wanted(self, files: Sequence[RemoteFile]) -> list[RemoteFile]:
        out = [f for f in files if f.file_type in self.file_types]
        if self.years:
            out = [f for f in out if self.years[0] <= f.year <= self.years[1]]
        return out

    def listing(self) -> list[RemoteFile]:
        """The remote index (network), or the cached one in offline mode."""
        if self.mode == "offline":
            manifest = self.read_manifest()
            files = [
                RemoteFile(**{k: v[k] for k in ("file_type", "year", "created", "name")})
                for v in manifest["files"].values()
            ]
            return self._wanted(files)
        with urlopen(http_request(ROOT), timeout=60) as response:
            html = response.read().decode("utf-8", errors="replace")
        return self._wanted(parse_listing(html))

    def paths(self) -> dict[tuple[str, int], Path]:
        """Local path per (file_type, year) after ``prefetch``."""
        manifest = self.read_manifest()
        out = {}
        for entry in manifest["files"].values():
            if entry["file_type"] in self.file_types and (
                not self.years or self.years[0] <= entry["year"] <= self.years[1]
            ):
                out[(entry["file_type"], entry["year"])] = (
                    self.directory / entry["file_type"] / entry["name"]
                )
        return out

    def prefetch(self, *, progress: bool = False) -> dict[str, Any]:
        """Download missing files, verify cached ones; return the manifest subset used."""
        manifest = self.read_manifest()
        files = manifest.setdefault("files", {})
        used: dict[str, Any] = {}
        for remote in self.listing():
            key = f"{remote.file_type}/{remote.year}"
            entry = files.get(key)
            target = self.directory / remote.file_type / remote.name
            fresh = entry is not None and entry["name"] == remote.name and target.exists()
            if fresh and self.mode != "refresh":
                if file_checksum(target) != entry["sha256"]:
                    raise RuntimeError(f"Storm Events cache checksum mismatch for {remote.name}")
                used[key] = entry
                continue
            if self.mode == "offline":
                raise FileNotFoundError(f"{remote.name} missing from {self.directory} (offline)")
            if progress:
                print(f"fetch {remote.name}")
            entry = self._download(remote, target)
            if (
                entry is not None
                and entry["name"] != remote.name
                and (self.directory / remote.file_type / entry["name"]).exists()
            ):
                pass
            old = files.get(key)
            if old and old["name"] != remote.name:
                (self.directory / remote.file_type / old["name"]).unlink(missing_ok=True)
            files[key] = entry
            used[key] = entry
            self._write_manifest(manifest)
        manifest["retrieved_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        manifest["terms_url"] = TERMS_URL
        manifest["citation"] = CITATION
        self._write_manifest(manifest)
        return {"files": used, "terms_url": TERMS_URL, "citation": CITATION}

    def _download(self, remote: RemoteFile, target: Path) -> dict[str, Any]:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=target.parent, prefix="download-", suffix=".tmp")
        temp = Path(name)
        try:
            with (
                os.fdopen(fd, "wb") as handle,
                urlopen(http_request(remote.url), timeout=300) as response,
            ):
                while chunk := response.read(1 << 20):
                    handle.write(chunk)
                headers = dict(response.headers)
            length = headers.get("Content-Length")
            if length is not None and temp.stat().st_size != int(length):
                raise RuntimeError(f"incomplete download: {remote.name}")
            os.chmod(temp, 0o644)
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
        return {
            "file_type": remote.file_type,
            "year": remote.year,
            "created": remote.created,
            "name": remote.name,
            "url": remote.url,
            "sha256": file_checksum(target),
            "bytes": target.stat().st_size,
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
