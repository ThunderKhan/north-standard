"""Deterministic serialization and hashing helpers.

Settlement-critical objects must hash identically across repeated runs. This module
uses a deliberately small JSON canonicalization profile for the v0.1 research code:
sorted keys, UTF-8, no insignificant whitespace, and no NaN/Infinity values.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON text for a supported Python object."""

    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    """Return a lowercase SHA-256 hex digest of the canonical JSON representation."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
