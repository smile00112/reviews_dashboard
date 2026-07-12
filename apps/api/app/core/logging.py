"""Application logging setup (feature 010).

Stdlib only (constitution V). Call ``setup_logging()`` once at startup; module
code uses ``logging.getLogger(__name__)``. Never log credentials, storage-state
contents, or unredacted proxy URLs (constitution: Security & Credentials).
"""

import logging

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _CONFIGURED = True
