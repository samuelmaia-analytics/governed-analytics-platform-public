"""Read and search a closed, content-authorized public governance corpus."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import unicodedata
from pathlib import Path

from src.governance_rag import Hit, LocalIndex, RagError, contains_sensitive_content
from src.public_revocation import content_not_revoked

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "config/public_governance_rag.json"
SOURCE_VERSION = 1
PURPOSE = "public_governance_rag"
SOURCES = tuple(
    f"docs/public-rag/{topic}.md"
    for topic in (
        "data-contracts",
        "data-quality",
        "layers",
        "quarantine",
        "lgpd",
        "publication-gate",
    )
)
MAX_SOURCE_BYTES = 1200
MAX_QUESTION_CHARS = 400

_UNSAFE_CONTENT = re.compile(
    r"[<>\x00-\x08\x0b-\x0c\x0e-\x1f]|https?://|javascript:|"
    r"\b(?:ignore|disregard|override|desconsidere|ignorar)\b.{0,40}"
    r"\b(?:instructions?|rules?|instrucoes|regras)\b|"
    r"\b(?:reveal|exfiltrate|divulgue|revele)\b.{0,40}"
    r"\b(?:secrets?|credentials?|segredos?|credenciais|prompts?)\b|"
    r"\b\d{11}\b|\b(?:\+?55[ .-]?)?\(?\d{2}\)?[ .-]?9?\d{4}[ .-]\d{4}\b",
    re.DOTALL,
)


def _unsafe(text: str) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )
    return contains_sensitive_content(normalized) or bool(
        _UNSAFE_CONTENT.search(normalized)
    )


def _read_fixed_path(root: Path, relative: str, limit: int) -> bytes:
    expected = root.absolute() / relative
    current = expected
    while current != current.parent:
        metadata = current.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Redirected path")
        current = current.parent
    if expected.resolve(strict=True) != expected or not stat.S_ISREG(
        expected.stat().st_mode
    ):
        raise ValueError("Unexpected source path")
    with expected.open("rb") as handle:
        data = handle.read(limit + 1)
    if not data or len(data) > limit:
        raise ValueError("Invalid artifact size")
    return data


def _unique_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(items)
    if len(result) != len(items):
        raise ValueError("Duplicate manifest key")
    return result


def load_public_sources(root: Path = PROJECT_ROOT) -> tuple[tuple[str, str, str], ...]:
    """Return a fresh, all-or-nothing snapshot of authorized text and exact hashes."""
    try:
        descriptor = json.loads(
            _read_fixed_path(root, MANIFEST, 8192), object_pairs_hook=_unique_keys
        )
        if (
            not isinstance(descriptor, dict)
            or type(descriptor.get("version")) is not int
        ):
            raise ValueError("Invalid manifest")
        entries = descriptor.get("files")
        if (
            descriptor["version"] != 1
            or not isinstance(entries, dict)
            or set(entries) != set(SOURCES)
        ):
            raise ValueError("Unexpected source set")
        snapshot = []
        for path in SOURCES:
            entry = entries[path]
            if (
                not isinstance(entry, dict)
                or type(entry.get("version")) is not int
                or entry["version"] != SOURCE_VERSION
                or entry.get("audience") != "public"
                or entry.get("purpose") != PURPOSE
                or entry.get("status") != "Approved"
                or entry.get("publication_authorized") is not True
            ):
                raise ValueError("Missing publication grant")
            raw = _read_fixed_path(root, path, MAX_SOURCE_BYTES)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != entry.get("sha256") or not content_not_revoked(
                raw, root=root, artifact=path
            ):
                raise ValueError("Source integrity check failed")
            text = raw.decode("utf-8")
            if _unsafe(text):
                raise ValueError("Unsafe source text")
            snapshot.append((path, digest, text))
        return tuple(snapshot)
    except (OSError, ValueError, RecursionError):
        raise RagError("Public corpus unavailable.") from None


def retrieve_public_evidence(index: LocalIndex, question: str) -> tuple[Hit, ...]:
    if len(question) > MAX_QUESTION_CHARS or _unsafe(question):
        raise RagError("Invalid visitor question.")
    return index.retrieve(question, top_k=3, min_term_coverage=0.75)
