"""Fail-closed security checks with metadata-only console output."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

IMAGE = "ghcr.io/gitleaks/gitleaks:v8.30.1"


def classify(stage: str, code: int, report: object) -> str:
    if stage == "dependencies":
        if not isinstance(report, dict) or not isinstance(
            report.get("dependencies"), list
        ):
            return "operational_error"
        deps = report["dependencies"]
        if any(not isinstance(d, dict) for d in deps):
            return "operational_error"
        if code in (0, 1) and any(d.get("vulns") for d in deps):
            return "vulnerabilities"
        if any(d.get("skip_reason") for d in deps):
            return "incomplete_audit"
        return "pass" if code == 0 else "operational_error"
    if not isinstance(report, list):
        return "operational_error"
    if code == 10 and report:
        return "secret_findings"
    return "pass" if code == 0 and not report else "operational_error"


def execute(command: list[str]) -> int:
    # Never forward scanner output, including exception text, to Actions logs.
    return subprocess.run(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode


def check(stage: str) -> int:
    code = -1
    category = "operational_error"
    try:
        with tempfile.TemporaryDirectory(prefix="gap-security-") as folder:
            root = Path(folder)
            report = root / "findings.json"
            if stage == "dependencies":
                requirements = root / "requirements.txt"
                code = execute(
                    [
                        "uv",
                        "export",
                        "--locked",
                        "--all-extras",
                        "--no-emit-project",
                        "--format",
                        "requirements-txt",
                        "--output-file",
                        str(requirements),
                    ]
                )
                if code != 0:
                    raise RuntimeError
                code = execute(
                    [
                        "uv",
                        "run",
                        "--no-sync",
                        "pip-audit",
                        "--progress-spinner",
                        "off",
                        "--requirement",
                        str(requirements),
                        "--no-deps",
                        "--disable-pip",
                        "--format",
                        "json",
                        "--output",
                        str(report),
                    ]
                )
            else:
                archive = root / "source.zip"
                code = execute(
                    ["git", "archive", "--format=zip", "--output", str(archive), "HEAD"]
                )
                if code != 0:
                    raise RuntimeError
                source = root / "source"
                source.mkdir()
                with zipfile.ZipFile(archive) as contents:
                    contents.extractall(source)
                code = execute(["docker", "pull", IMAGE])
                if code != 0:
                    raise RuntimeError
                output = root / "output"
                output.mkdir()
                report = output / "findings.json"
                code = execute(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "-v",
                        f"{source}:/scan:ro",
                        "-v",
                        f"{output}:/report:rw",
                        IMAGE,
                        "dir",
                        "/scan",
                        "--redact=100",
                        "--no-banner",
                        "--exit-code",
                        "10",
                        "--report-format",
                        "json",
                        "--report-path",
                        "/report/findings.json",
                    ]
                )
            category = classify(
                stage, code, json.loads(report.read_text(encoding="utf-8"))
            )
    except Exception:
        category = "operational_error"
    print(f"stage={stage} category={category} exit_code={code}")
    return 0 if category == "pass" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["dependencies", "secrets"])
    raise SystemExit(check(parser.parse_args().stage))
