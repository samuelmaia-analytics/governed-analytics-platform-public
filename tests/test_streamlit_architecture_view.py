import hashlib
import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest
from streamlit.testing.v1 import AppTest

from src import streamlit_architecture_view as view

PAYLOAD = b"<svg/>"
ALLOW = b'{"version":1,"revoked_sha256":[],"revoked_artifacts":[]}'


class Response(BytesIO):
    def __init__(
        self, data, *, status=200, media="application/octet-stream", length=None
    ):
        super().__init__(data)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = media
        if length is not None:
            self.headers["Content-Length"] = str(length)


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setenv("GAP_STREAMLIT_ARCHITECTURE_VIEW", "official_gap_streamlit")
    monkeypatch.setenv("GAP_RUNTIME_ASSET_TOKEN", "github_pat_fixture")
    monkeypatch.setitem(
        view.APPROVED_SHA256, "azure", hashlib.sha256(PAYLOAD).hexdigest()
    )
    requests = []
    responses = [Response(PAYLOAD), Response(ALLOW)]

    class Opener:
        def open(self, request, *, timeout):
            assert timeout == 4.0
            assert request.full_url.startswith(view._CONTENTS_API)
            assert request.get_header("Authorization") == "Bearer github_pat_fixture"
            assert request.get_header("Cache-control") == "no-cache, no-store"
            requests.append(request.full_url.removeprefix(view._CONTENTS_API))
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(view, "build_opener", lambda *_handlers: Opener())
    return requests, responses


def test_live_policy_is_queried_for_each_delivery(runtime):
    requests, responses = runtime
    assert view.read_architecture_view("azure") == PAYLOAD
    deny = json.dumps(
        {
            "version": 1,
            "revoked_sha256": [hashlib.sha256(PAYLOAD).hexdigest()],
            "revoked_artifacts": [],
        }
    ).encode()
    responses.extend([Response(PAYLOAD), Response(deny)])
    assert view.read_architecture_view("azure") is None
    assert (
        requests
        == ["azure-reference-architecture.svg?ref=main", "revocations.json?ref=main"]
        * 2
    )


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500, 503])
@pytest.mark.parametrize("policy_failure", [False, True])
def test_failed_transport_never_delivers(runtime, status, policy_failure):
    _, responses = runtime
    responses[int(policy_failure)] = HTTPError(
        view._CONTENTS_API, status, "fixture", {}, None
    )
    assert view.read_architecture_view("azure") is None


@pytest.mark.parametrize(
    "failure",
    [
        "timeout",
        "unavailable",
        "mismatch",
        "type",
        "size",
        "stream_size",
        "truncated",
        "invalid_policy",
    ],
)
def test_bad_response_blocks_view(runtime, failure):
    _, responses = runtime
    if failure == "invalid_policy":
        responses[1] = Response(b"invalid")
    else:
        responses[0] = {
            "timeout": TimeoutError(),
            "unavailable": URLError("fixture"),
            "mismatch": Response(b"<svg>other</svg>"),
            "type": Response(PAYLOAD, media="text/html"),
            "size": Response(PAYLOAD, length=view._MAX_BYTES + 1),
            "stream_size": Response(b"x" * (view._MAX_BYTES + 1)),
            "truncated": Response(PAYLOAD, length=len(PAYLOAD) + 1),
        }[failure]
    assert view.read_architecture_view("azure") is None


def test_unapproved_context_and_paths_never_make_requests(runtime, monkeypatch):
    requests, _ = runtime
    assert view.read_architecture_view("../azure") is None
    monkeypatch.delenv("GAP_RUNTIME_ASSET_TOKEN")
    assert view.read_architecture_view("azure") is None
    monkeypatch.setenv("GAP_RUNTIME_ASSET_TOKEN", "github_pat_fixture")
    monkeypatch.setenv("GAP_STREAMLIT_ARCHITECTURE_VIEW", "unapproved")
    assert view.read_architecture_view("azure") is None
    assert requests == []
    assert (
        view._NoRedirect().redirect_request(
            None, None, 302, "", {}, "https://example.org"
        )
        is None
    )


def test_unavailable_diagram_keeps_text_alternative(monkeypatch):
    monkeypatch.setenv("GAP_PUBLIC_VISITOR_MODE", "true")
    monkeypatch.setenv("GAP_STREAMLIT_ARCHITECTURE_VIEW", "official_gap_streamlit")
    monkeypatch.delenv("GAP_RUNTIME_ASSET_TOKEN", raising=False)
    app = AppTest.from_string(
        "from app.pages.public_architecture import render_public_architecture\n"
        'render_public_architecture("azure")'
    ).run()
    assert not app.exception
    assert not app.get("download_button")
    assert any(
        node.value == "Diagram unavailable for this session." for node in app.info
    )
    assert any(item.label == "Accessible text alternative" for item in app.expander)


def test_github_raw_vendor_media_type(runtime):
    _, responses = runtime
    responses[:] = [
        Response(PAYLOAD, media="application/vnd.github.raw+json; charset=utf-8"),
        Response(ALLOW, media="application/vnd.github.raw+json; charset=utf-8"),
    ]
    assert view.read_architecture_view("azure") == PAYLOAD
