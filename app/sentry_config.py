"""Sentry initialization.

Called once at startup. If SENTRY_DSN isn't set, this is a silent no-op rather than an
error — Sentry is meant to be optional infrastructure
"""

import os

import sentry_sdk


def configure_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
