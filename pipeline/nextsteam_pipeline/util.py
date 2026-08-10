from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def stable_id(prefix: str, *parts: object) -> str:
    value = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value
    if is_dataclass(value) and not isinstance(value, type):
        payload = asdict(value)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)
