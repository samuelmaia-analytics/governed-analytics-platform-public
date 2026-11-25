import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.sync.client import connect


def test_streamlit_websocket_accepts_non_ascii_forwarded_header(tmp_path):
    script = tmp_path / "app.py"
    script.write_text(
        'import streamlit as st\nst.title("Runtime smoke test")\n', encoding="utf-8"
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    address = f"127.0.0.1:{port}"
    logs = tmp_path / "streamlit.log"
    with logs.open("wb") as output:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(script),
                "--server.headless=true",
                "--server.address=127.0.0.1",
                f"--server.port={port}",
                "--browser.gatherUsageStats=false",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(
                        f"http://{address}/_stcore/health", timeout=1
                    ) as health:
                        assert health.status == 200
                    break
                except URLError:
                    if server.poll() is not None or time.monotonic() >= deadline:
                        pytest.fail(logs.read_text(encoding="utf-8", errors="replace"))
                    time.sleep(0.05)

            with connect(
                f"ws://{address}/_stcore/stream",
                subprotocols=["streamlit"],
                additional_headers={"X-Forwarded-User": "caf\u00e9"},
                open_timeout=5,
                close_timeout=1,
            ) as websocket:
                request = BackMsg()
                request.rerun_script.SetInParent()
                websocket.send(request.SerializeToString())
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    response = ForwardMsg.FromString(
                        websocket.recv(timeout=5, decode=False)
                    )
                    if response.delta.new_element.heading.body == "Runtime smoke test":
                        break
                else:
                    pytest.fail("Streamlit did not send the rendered heading")
        finally:
            server.terminate()
            server.wait(timeout=10)

    assert "can abort the /_stcore/stream" not in logs.read_text(encoding="utf-8")
