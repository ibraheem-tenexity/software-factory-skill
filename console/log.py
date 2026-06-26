"""Logging configuration for the console package.

Usage:
    from console.log import get_logger
    log = get_logger(__name__)
    log.info("server started")
    log.exception("unhandled error")  # prints traceback to stdout
"""
import logging
import sys


def _configure_root() -> None:
    root = logging.getLogger("console")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False


_configure_root()


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
