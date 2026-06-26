"""Logging configuration for the software_factory package.

Usage:
    from software_factory.log import get_logger
    log = get_logger(__name__)
    log.info("started")
    log.exception("something broke")  # prints traceback to stdout
"""
import logging
import sys


def _configure_root() -> None:
    root = logging.getLogger("software_factory")
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
