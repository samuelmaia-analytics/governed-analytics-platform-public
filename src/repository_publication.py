"""Check candidate files and Git trees before distributing source artifacts."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = "config/distribution_inventory.json"
PUBLIC_POLICY = "config/public_distribution_policy.json"
SAFE_DATA = {
    "data/README.md",
    "data/published/monitoring/publication_decision.json",
}
BLOCKED_SUFFIXES = {
    ".csv",
    ".parquet",
    ".jsonl",
    ".pbix",
    ".pbit",
    ".pdf",
    ".docx",
    ".xlsx",
}


MAIN_REF = "refs/heads/main"


def _is_hex_oid(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{40}", value))


def _is_zero_oid(value: str) -> bool:
    return set(value) == {"0"}


def _parse_pre_push_updates(lines: list[str]) -> tuple[str, str, str, str]:
    if len(lines) != 1:
        raise ValueError("Only a single ref update is supported per push.")
    parts = lines[0].split()
    if len(parts) != 4:
        raise ValueError("Malformed pre-push update line.")
    return parts[0], parts[1], parts[2], parts[3]


def _confirm_allowed_remote(
    root: Path, remote_name: str | None, remote_url: str | None
) -> str:
    if not remote_name or not remote_url:
        raise ValueError("Missing pre-push remote context.")
    if remote_name != "origin":
        raise ValueError("Push remote must be origin.")
    configured = (
        git(root, "remote", "get-url", "--push", "--all", "origin")
        .decode()
        .splitlines()
    )
    if remote_url not in configured:
        raise ValueError("Push destination differs from the configured origin URL.")
    return remote_url


def _load_trusted_policy(root: Path, remote_url: str) -> dict:
    tracking = git(root, "rev-parse", "refs/remotes/origin/main").decode().strip()
    if not _is_hex_oid(tracking):
        raise ValueError("Unable to resolve refs/remotes/origin/main.")

    advertised = git(root, "ls-remote", remote_url, MAIN_REF).decode().split()
    if (
        len(advertised) < 2
        or advertised[1] != MAIN_REF
        or not _is_hex_oid(advertised[0])
    ):
        raise ValueError("Unable to confirm origin/main identity via ls-remote.")
    if advertised[0] != tracking:
        raise ValueError(
            "origin/main differs from the advertised remote main; run git fetch origin."
        )

    return json.loads(git(root, "show", f"{tracking}:{INVENTORY}"))


def _dev_branch_pre_push_problems(
    root: Path,
    *,
    remote_url: str,
    local_ref: str,
    tip: str,
    remote_ref: str,
    base: str,
) -> list[str]:
    if local_ref != remote_ref:
        raise ValueError("Refspec rewriting is not allowed during governed pushes.")
    if local_ref == MAIN_REF or remote_ref == MAIN_REF:
        raise ValueError("Pushes involving main must target main only.")
    if not (
        local_ref.startswith("refs/heads/") and remote_ref.startswith("refs/heads/")
    ):
        raise ValueError("Only branch refs under refs/heads are allowed.")
    if not _is_hex_oid(tip) or _is_zero_oid(tip):
        raise ValueError("Branch creation/deletion with an empty tip is not allowed.")
    if not _is_hex_oid(base):
        raise ValueError("Malformed remote base object id.")

    if git(root, "cat-file", "-t", tip).decode().strip() != "commit":
        raise ValueError("Tip is not a commit object.")
    if (
        not _is_zero_oid(base)
        and git(root, "cat-file", "-t", base).decode().strip() != "commit"
    ):
        raise ValueError("Remote base is not a commit object.")

    if not _is_zero_oid(base):
        git(root, "merge-base", "--is-ancestor", base, tip)

    policy = _load_trusted_policy(root, remote_url)
    reachable = set(
        git(root, "rev-list", "--objects", "--no-object-names", tip)
        .decode()
        .splitlines()
    )
    if reachable.intersection(policy["restricted_git_blobs"]):
        return ["Restricted audited blobs are reachable from the proposed tip."]

    final_files, final_modes = candidate_snapshot(root, tip)
    if json.loads(final_files.get(INVENTORY, b"null")) != policy:
        return ["Final inventory differs from the active reviewed policy."]

    problems = [
        f"{tip}: {p}"
        for p in snapshot_problems(final_files, final_modes, policy=policy)
    ]

    # The final tree always receives the full strict check. Additionally, scan
    # every outgoing commit so prohibited content cannot be introduced and then
    # removed before the tip.
    if _is_zero_oid(base):
        tracking = git(root, "rev-parse", "refs/remotes/origin/main").decode().strip()
        commit_lines = (
            git(
                root,
                "rev-list",
                "--reverse",
                "--topo-order",
                "--parents",
                f"{tracking}..{tip}",
            )
            .decode()
            .splitlines()
        )
    else:
        commit_lines = (
            git(
                root,
                "rev-list",
                "--reverse",
                "--topo-order",
                "--parents",
                f"{base}..{tip}",
            )
            .decode()
            .splitlines()
        )

    for line in commit_lines:
        revision, *_parents = line.split()
        if revision == tip:
            continue
        files, modes = candidate_snapshot(root, revision)
        if json.loads(files.get(INVENTORY, b"null")) != policy:
            problems.append(
                f"{revision}: Inventory differs from the active reviewed policy."
            )
            continue
        problems.extend(
            f"{revision}: {p}" for p in snapshot_problems(files, modes, policy=policy)
        )
    return problems


def pre_push_problems(
    root: Path, lines: list[str], remote_name: str | None, remote_url: str | None
) -> list[str]:
    local_ref, tip, remote_ref, base = _parse_pre_push_updates(lines)

    if local_ref == MAIN_REF or remote_ref == MAIN_REF:
        if local_ref != MAIN_REF or remote_ref != MAIN_REF:
            raise ValueError("Pushes involving main must update main only.")
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from src.private_pre_push import private_pre_push_problems

        return private_pre_push_problems(root, lines, remote_name, remote_url)

    remote_url = _confirm_allowed_remote(root, remote_name, remote_url)
    return _dev_branch_pre_push_problems(
        root,
        remote_url=remote_url,
        local_ref=local_ref,
        tip=tip,
        remote_ref=remote_ref,
        base=base,
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def candidate_entries(root: Path, revision: str | None) -> dict[str, tuple[str, str]]:
    if revision == ":index":
        entries = {}
        for item in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if not item:
                continue
            metadata, path = item.decode().split("\t", 1)
            mode, oid, stage = metadata.split()
            if stage != "0":
                raise ValueError("Resolve unmerged index entries before publication.")
            entries[path] = (mode, oid)
        return entries
    if revision is not None:
        entries = {}
        for item in git(root, "ls-tree", "-r", "-z", revision).split(b"\0"):
            if item:
                metadata, path = item.decode().split("\t", 1)
                mode, _kind, oid = metadata.split()
                entries[path] = (mode, oid)
        return entries
    names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return {
        name.decode(): (
            "120000" if (root / name.decode()).is_symlink() else "100644",
            "",
        )
        for name in names.split(b"\0")
        if name
        and ((root / name.decode()).exists() or (root / name.decode()).is_symlink())
    }


def entry_content(root: Path, path: str, entry: tuple[str, str]) -> bytes:
    return (
        git(root, "cat-file", "blob", entry[1])
        if entry[1]
        else (root / path).read_bytes()
    )


def candidate_snapshot(
    root: Path, revision: str | None = None, *, excluded_paths: set[str] | None = None
) -> tuple[dict[str, bytes], dict[str, str]]:
    entries = candidate_entries(root, revision)
    if excluded_paths:
        entries = {
            name: entry for name, entry in entries.items() if name not in excluded_paths
        }
    objects = {}
    if revision is not None:
        oids = sorted(
            {entry[1] for entry in entries.values() if entry[0] in {"100644", "100755"}}
        )
        output = subprocess.check_output(
            ["git", "-C", str(root), "cat-file", "--batch"],
            input=("\n".join(oids) + "\n").encode(),
        )
        stream = io.BytesIO(output)
        for oid in oids:
            actual_oid, kind, size = stream.readline().decode().split()
            if actual_oid != oid or kind != "blob":
                raise ValueError("Unexpected Git object in candidate snapshot.")
            objects[oid] = stream.read(int(size))
            if stream.read(1) != b"\n":
                raise ValueError("Invalid Git batch response.")
    files = {
        name: objects[entry[1]]
        if revision is not None
        else entry_content(root, name, entry)
        for name, entry in entries.items()
        if entry[0] in {"100644", "100755"}
    }
    return files, {name: entry[0] for name, entry in entries.items()}


def _fingerprint(kind: str, value: str) -> str:
    return hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()


def sanitized_distribution_policy(policy: dict) -> bytes:
    """Keep deny checks without exporting reviewed paths, raw object IDs or notes."""
    records = policy["excluded_files"]
    fixtures = policy.get("synthetic_test_fixtures", {})
    fingerprints = {
        _fingerprint("path", name.casefold())
        for name in [
            *(record["path"] for record in records),
            *fixtures,
            *policy.get("pending_reports", []),
        ]
    }
    fingerprints.update(
        _fingerprint("sha256", digest)
        for digest in [
            *(record["sha256"] for record in records),
            *(record["sha256"] for record in fixtures.values()),
            *policy.get("pending_report_variants_sha256", []),
            *policy.get("pending_content_variants_sha256", []),
        ]
    )
    fingerprints.update(
        _fingerprint("blob", oid)
        for oid in [
            *policy["restricted_git_blobs"],
            *(
                record["git_blob"]
                for record in [*records, *fixtures.values()]
                if "git_blob" in record
            ),
        ]
    )
    return (
        json.dumps(
            {"version": 1, "denied_fingerprints": sorted(fingerprints)}, indent=2
        )
        + "\n"
    ).encode()


def snapshot_problems(
    files: dict[str, bytes], modes: dict[str, str], *, policy: dict | None = None
) -> list[str]:
    fingerprints: set[str] = set()
    public_mode = INVENTORY not in files
    if public_mode:
        try:
            public_policy = json.loads(files[PUBLIC_POLICY])
            entries = public_policy["denied_fingerprints"]
            if (
                public_policy["version"] != 1
                or not isinstance(entries, list)
                or not entries
                or not all(
                    isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item)
                    for item in entries
                )
            ):
                raise ValueError
            fingerprints.update(entries)
        except (KeyError, ValueError, TypeError):
            return ["Public distribution policy missing or invalid."]
        policy = {"excluded_files": [], "restricted_git_blobs": []}
    elif policy is None:
        policy = json.loads(files[INVENTORY])
    records = policy["excluded_files"]
    blocked_paths = {item["path"].casefold() for item in records}
    blocked_digests = {item["sha256"] for item in records}
    blocked_digests.update(policy.get("pending_report_variants_sha256", []))
    blocked_digests.update(policy.get("pending_content_variants_sha256", []))
    blocked_blobs = set(policy["restricted_git_blobs"])
    blocked_blobs.update(item["git_blob"] for item in records if "git_blob" in item)
    legacy_fixtures = policy.get("synthetic_test_fixtures", {})
    blocked_paths.update(name.casefold() for name in legacy_fixtures)
    blocked_digests.update(item["sha256"] for item in legacy_fixtures.values())
    blocked_blobs.update(
        item["git_blob"] for item in legacy_fixtures.values() if "git_blob" in item
    )
    problems = []
    for name, mode in modes.items():
        path = Path(name)
        lower = name.casefold()
        if mode not in {"100644", "100755"}:
            problems.append(f"Unsupported symlink or submodule: {name}")
            continue
        if (
            lower in blocked_paths
            or _fingerprint("path", lower) in fingerprints
            or (
                lower.startswith("data/")
                and (public_mode or name not in SAFE_DATA)
                and path.name != ".gitkeep"
            )
            or (lower.startswith("logs/") and name != "logs/.gitkeep")
            or path.suffix.lower() in BLOCKED_SUFFIXES
            or lower.startswith(("dist/", ".git/", ".venv/", "docs/security/"))
            or path.name.casefold() == "secrets.toml"
            or (path.name.startswith(".env") and path.name != ".env.example")
        ):
            problems.append(f"Unauthorized distribution path: {name}")
            continue
        content = files[name]
        if b'"olist_rejection_journal"' in content:
            try:
                document = json.loads(content)
            except ValueError:
                document = None
            if (
                isinstance(document, dict)
                and document.get("kind") == "olist_rejection_journal"
            ):
                problems.append(f"Restricted quarantine journal: {name}")
                continue
        digest = hashlib.sha256(content).hexdigest()
        oid = hashlib.sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content
        ).hexdigest()
        reviewed_digest = policy.get("metadata_sha256", {}).get(name)
        if (
            name in SAFE_DATA
            and name != "data/README.md"
            and reviewed_digest != digest
            and policy.get("metadata_git_blobs", {}).get(name) != oid
        ):
            problems.append(f"Governance metadata requires review: {name}")
        if (
            oid in blocked_blobs
            or digest in blocked_digests
            or _fingerprint("blob", oid) in fingerprints
            or _fingerprint("sha256", digest) in fingerprints
        ):
            problems.append(f"Unauthorized content copy: {name}")
    return problems


def publication_problems(root: Path, revision: str | None = None) -> list[str]:
    return snapshot_problems(*candidate_snapshot(root, revision))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--index", action="store_true")
    mode.add_argument("--ref")
    mode.add_argument("--worktree", action="store_true")
    mode.add_argument("--pre-push", action="store_true")
    parser.add_argument("--remote-name")
    parser.add_argument("--remote-url")
    args = parser.parse_args()
    try:
        if args.pre_push:
            if not (ROOT / INVENTORY).is_file():
                raise ValueError("Private pre-push policy is unavailable.")
            problems = pre_push_problems(
                ROOT, sys.stdin.read().splitlines(), args.remote_name, args.remote_url
            )
        else:
            revisions = [":index" if args.index else args.ref]
            problems = [
                f"{revision or 'worktree'}: {problem}"
                for revision in revisions
                for problem in publication_problems(ROOT, revision)
            ]
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        print("FAIL: candidate tree could not be verified.", file=sys.stderr)
        return 1
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("PASS: publication checks completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
