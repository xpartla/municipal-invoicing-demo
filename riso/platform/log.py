"""Logging with the request ID (guide §6.10). Log IDs and states, never invoice text, names,
IBANs or file contents."""

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every record, from the request being served."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Sets up the root logger for `riso serve` and `riso worker`; tests leave logging alone."""
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
