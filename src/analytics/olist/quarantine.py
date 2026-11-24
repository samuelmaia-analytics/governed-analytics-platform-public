"""Restricted rejection journal for a single analytical build.

Remediate the source through the normal ingestion path and use a new execution
ID. A journal is evidence and is never a source for reprocessing.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

RejectRows = Callable[[str, pd.DataFrame], None]


def exclude_rows(
    frame: pd.DataFrame,
    rejected: pd.Series,
    rule: str,
    reject: RejectRows | None,
) -> pd.DataFrame:
    if reject is not None and rejected.any():
        reject(rule, frame.loc[rejected])
    return frame.loc[~rejected].copy()


class RejectionJournal:
    def __init__(self, directory: Path, run_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
            raise ValueError("Invalid quarantine execution ID.")
        self.path = directory / f"build-{run_id}.json"
        self.run_id = run_id
        self.rejections: list[dict[str, object]] = []

    def capture(self, dataset: str, rule: str, rows: pd.DataFrame) -> None:
        self.rejections.append(
            {
                "dataset": dataset,
                "rule": rule,
                "input_index": rows.index.tolist(),
                "records": json.loads(
                    rows.to_json(
                        orient="records", date_format="iso", double_precision=15
                    )
                ),
            }
        )

    def persist(self) -> None:
        if not self.rejections and not self.path.exists():
            return
        payload = json.dumps(
            {
                "version": 1,
                "kind": "olist_rejection_journal",
                "audience": "internal_restricted",
                "publication_authorized": False,
                "remediation_owner": "Data Governance",
                "retention_review_required": True,
                "run_id": self.run_id,
                "stage": "build",
                "rejections": self.rejections,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        ).encode("utf-8")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            dir=self.path.parent, prefix=".quarantine-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                # Atomically publish the complete local journal without overwriting
                # evidence from a concurrent run or a previous attempt.
                os.link(temporary, self.path)
            except FileExistsError:
                if self.path.read_bytes() != payload:
                    raise ValueError(
                        "Quarantine execution ID already has different evidence."
                    ) from None
            finally:
                stream.close()
                temporary.unlink()
