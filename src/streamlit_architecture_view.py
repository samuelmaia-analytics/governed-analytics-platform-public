"""Read exact, view-only SVGs and live revocations from the private runtime repository."""

from __future__ import annotations

import hashlib
import os
from http.client import HTTPException
from time import monotonic
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from src.public_mode import is_public_visitor_mode
from src.public_revocation import policy_allows

APPROVED_SHA256 = {
    "azure": "3bdd46130674b0708cfafde29018cf23d2d4b715ae0be5b7a279fad30d2cbc1e",
    "aws": "fd4f7e134afd49ced814bcb443b702b24dc9d8811c87087cf3c785b5a42b3f75",
}
_CONTENTS_API = (
    "https://api.github.com/repos/samuelmaia-analytics/gap-runtime-assets/contents/"
)
_FILES = {
    "revocations.json",
    *(f"{provider}-reference-architecture.svg" for provider in APPROVED_SHA256),
}
_MAX_BYTES = 256 * 1024
_TIMEOUT = 4.0
_RAW_TYPES = {
    "application/octet-stream",
    "application/json",
    "image/svg+xml",
    "text/plain",
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def architecture_view_enabled() -> bool:
    return (
        is_public_visitor_mode()
        and os.environ.get("GAP_STREAMLIT_ARCHITECTURE_VIEW")
        == "official_gap_streamlit"
    )


def _read_runtime_file(name: str, token: str) -> bytes:
    if name not in _FILES:
        raise ValueError("Unapproved runtime path")
    request = Request(
        _CONTENTS_API + name + "?ref=main",
        headers={
            "Accept": "application/vnd.github.raw+json",
            "Authorization": f"Bearer {token}",
            "Cache-Control": "no-cache, no-store",
            "Accept-Encoding": "identity",
        },
    )
    # Do not forward credentials through ambient proxy or redirect configuration.
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    deadline = monotonic() + _TIMEOUT
    with opener.open(request, timeout=_TIMEOUT) as response:
        if (
            response.status != 200
            or response.headers.get_content_type() not in _RAW_TYPES
        ):
            raise ValueError("Unexpected runtime response")
        if response.headers.get("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("Unexpected content encoding")
        declared = response.headers.get("Content-Length")
        size = int(declared) if declared is not None else None
        if size is not None and not 0 < size <= _MAX_BYTES:
            raise ValueError("Unacceptable runtime size")
        body = bytearray()
        while True:
            part = response.read1(min(8192, _MAX_BYTES + 1 - len(body)))
            body.extend(part)
            if monotonic() >= deadline or len(body) > _MAX_BYTES:
                raise ValueError("Runtime response exceeded bounds")
            if not part:
                break
        if not body or (size is not None and len(body) != size):
            raise ValueError("Incomplete runtime response")
        return bytes(body)


def read_architecture_view(provider: str) -> bytes | None:
    if not architecture_view_enabled() or provider not in APPROVED_SHA256:
        return None
    token = os.environ.get("GAP_RUNTIME_ASSET_TOKEN", "").strip()
    if not token.startswith("github_pat_"):
        return None
    name = f"{provider}-reference-architecture.svg"
    try:
        content = _read_runtime_file(name, token)
        if hashlib.sha256(content).hexdigest() != APPROVED_SHA256[provider]:
            return None
        # Read current policy after fetching bytes. Never reuse an earlier allow decision.
        if not policy_allows(
            _read_runtime_file("revocations.json", token),
            content,
            artifact=f"docs/assets/architecture/{name}",
        ):
            return None
        return content
    except HTTPError as exc:
        exc.close()
        return None
    except (OSError, HTTPException, ValueError):
        return None
