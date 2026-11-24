from __future__ import annotations

import os


def is_public_visitor_mode() -> bool:
    """Return True when running the public visitor profile.

    The public repository historically used the name `GAP_PUBLIC_DEMO_MODE`. The
    product is not a demo: keep the legacy flag as an alias while promoting the
    visitor naming going forward.
    """

    def _truthy(value: str | None) -> bool:
        return (value or "").strip().lower() == "true"

    return _truthy(os.environ.get("GAP_PUBLIC_VISITOR_MODE")) or _truthy(
        os.environ.get("GAP_PUBLIC_DEMO_MODE")
    )
