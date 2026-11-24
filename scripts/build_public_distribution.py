"""Build a reviewed source package from candidate files, excluding local data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.public_revocation import policy_allows
from src.repository_publication import (
    INVENTORY,
    PUBLIC_POLICY,
    ROOT,
    candidate_snapshot,
    sanitized_distribution_policy,
    snapshot_problems,
)

PRIVATE_FILES = {
    INVENTORY,
    "src/private_pre_push.py",
    ".gitattributes",
    ".dockerignore",
}


def _selection(files: dict[str, bytes]) -> tuple[dict[str, bytes], list[str]]:
    """Select the current repository's explicitly scoped public source files."""
    scope = json.loads(files["config/public_scope.json"])
    registry = json.loads(files["config/public_distribution.json"])
    repository = "samuelmaia-analytics/Governed-Analytics-Platform"
    if (
        scope.get("repository") != repository
        or registry.get("repository") != repository
    ):
        raise ValueError("Public scope and authorizations must belong to GAP.")
    selected = {}
    pending = []
    private_contents = {files[name] for name in PRIVATE_FILES if name in files}
    for name, content in files.items():
        if (
            name in PRIVATE_FILES
            or name.startswith(".githooks/")
            or content in private_contents
        ):
            continue
        if name in scope["private_test_modules"]:
            continue
        if name.startswith("tests/") and name not in scope["public_tests"]:
            continue
        digest = hashlib.sha256(content).hexdigest()
        if name.endswith((".csv", ".parquet", ".jsonl")):
            # Dataset files stay outside this source-only distribution.
            continue
        if name.startswith("docs/"):
            if scope["documents"].get(name) != digest:
                continue
            grant = {
                "dataset": name,
                "version": digest,
                "sha256": digest,
                "purpose": "documentation_preview",
                "audience": "public",
            }
            if not any(
                isinstance(item, dict)
                and item.get("status") == "Approved"
                and item.get("publication_authorized") is True
                and all(item.get(key) == value for key, value in grant.items())
                for item in registry.get("authorizations", [])
            ):
                pending.append(name)
        elif name.startswith(
            ("assets/", "images/", "presentation/", "data/screenshots/")
        ):
            if scope["assets"].get(name) != digest:
                continue
        elif name.startswith("data/") and name not in scope["data_metadata"]:
            continue
        elif "/" not in name and name not in scope["root_files"]:
            continue
        elif "/" in name and not name.startswith(
            ("docs/", "assets/", "data/", *scope["code_prefixes"])
        ):
            continue
        selected[name] = content
    missing = (set(scope["documents"]) | set(scope["assets"])) - selected.keys()
    if missing:
        raise ValueError("Reviewed public documents or assets have changed.")
    readme_source = scope["readme_source"]
    if readme_source not in scope["documents"] or readme_source not in selected:
        raise ValueError("Public README must be a reviewed document.")
    selected["README.md"] = selected[readme_source]
    if INVENTORY in files:
        private_policy = json.loads(files[INVENTORY])
        selected[PUBLIC_POLICY] = sanitized_distribution_policy(private_policy)
        if ".gitignore" in selected:
            held_paths = {
                *(record["path"] for record in private_policy["excluded_files"]),
                *private_policy.get("synthetic_test_fixtures", {}),
            }
            rules = selected[".gitignore"].decode("utf-8").splitlines()
            rules = [rule for rule in rules if rule.lstrip("!/") not in held_paths]
            rules.extend(
                ["/tests/fixtures/", "/docs/reports/", "/docs/governance/lgpd*.md"]
            )
            selected[".gitignore"] = ("\n".join(rules) + "\n").encode()
        registry["authorizations"] = [
            {
                key: item[key]
                for key in (
                    "dataset",
                    "version",
                    "sha256",
                    "purpose",
                    "audience",
                    "status",
                    "publication_authorized",
                )
                if key in item
            }
            for item in registry["authorizations"]
            if isinstance(item, dict)
            and scope["documents"].get(item.get("dataset")) == item.get("sha256")
            and item.get("sha256") is not None
            and item.get("purpose") == "documentation_preview"
            and item.get("audience") == "public"
        ]
        selected["config/public_distribution.json"] = (
            json.dumps(registry, indent=2) + "\n"
        ).encode()
        visitor_name = "config/public_visitor_content.json"
        visitor = json.loads(files[visitor_name])
        visitor["files"] = {
            name: entry
            for name, entry in visitor["files"].items()
            if entry.get("approved") is True
            and entry.get("audience") == "public"
            and name in selected
        }
        selected[visitor_name] = (json.dumps(visitor, indent=2) + "\n").encode()
    policies = [files.get("config/public_revocations.json", b"")]
    override = os.environ.get("GAP_PUBLIC_REVOCATIONS_PATH")
    if override is not None:
        try:
            policies.append(Path(override).read_bytes())
        except OSError as exc:
            raise ValueError("Public revocation policy is unavailable.") from exc
    for name, content in selected.items():
        if not all(
            policy_allows(policy, content, artifact=name) for policy in policies
        ):
            raise ValueError(f"Revoked artifact or invalid revocation policy: {name}")
    return selected, sorted(pending)


def public_snapshot(files: dict[str, bytes]) -> dict[str, bytes]:
    selected, pending = _selection(files)
    if pending:
        raise ValueError("Documentation authorization missing: " + ", ".join(pending))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Report scope and missing grants without producing a ZIP.",
    )
    args = parser.parse_args()
    files, modes = candidate_snapshot(ROOT, ":index")
    if INVENTORY not in files:
        raise SystemExit(
            "The private review inventory is required to prepare a release."
        )
    problems = snapshot_problems(files, modes)
    if problems:
        raise SystemExit("\n".join(problems))
    selected, pending = _selection(files)
    selected_modes = {name: modes.get(name, "100644") for name in selected}
    problems = snapshot_problems(selected, selected_modes)
    if problems:
        raise SystemExit("\n".join(problems))
    if args.preview:
        print(
            json.dumps(
                {
                    "files": {
                        name: hashlib.sha256(content).hexdigest()
                        for name, content in sorted(selected.items())
                    },
                    "pending_document_authorizations": pending,
                },
                indent=2,
            )
        )
        return
    if pending:
        raise SystemExit("Documentation authorization missing: " + ", ".join(pending))
    # The exact validated snapshot is written without reopening source files.
    output = ROOT / "dist/gap-source.zip"
    output.parent.mkdir(exist_ok=True)
    temporary = output.with_suffix(".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(selected.items()):
                member = zipfile.ZipInfo(name)
                member.create_system = 3
                permissions = 0o755 if selected_modes[name] == "100755" else 0o644
                member.external_attr = (stat.S_IFREG | permissions) << 16
                archive.writestr(member, content, compress_type=zipfile.ZIP_DEFLATED)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print("Created dist/gap-source.zip from verified candidate files.")


if __name__ == "__main__":
    main()
