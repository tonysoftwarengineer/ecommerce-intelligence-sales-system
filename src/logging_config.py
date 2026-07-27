from __future__ import annotations

import logging
import os

DEFAULT_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """
    Configure root logging once, at process start.

    Individual modules should never call this -- they just do
    `logger = logging.getLogger(__name__)` and inherit this configuration.
    That keeps log setup a single entry-point concern rather than something
    each module re-decides.
    """
    logging.basicConfig(
        level=(level or os.environ.get("LOG_LEVEL", DEFAULT_LEVEL)).upper(),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
    )
