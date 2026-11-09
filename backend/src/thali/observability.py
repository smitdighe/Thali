import logging
from contextvars import ContextVar
lazy import json
lazy import sys
lazy import time
lazy import uuid
lazy from datetime import UTC, datetime

lazy from starlette.datastructures import Headers, MutableHeaders
lazy from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

EVENT_LOGGER = logging.getLogger("thali.events")
ROOT_LOGGER_NAME = "thali"
HANDLER_MARK = "_thali_json_handler"
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_LENGTH = 12


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, HANDLER_MARK, False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    setattr(handler, HANDLER_MARK, True)
    logger.addHandler(handler)
    logger.setLevel(level.upper())


def log_event(event: str, **fields: object) -> None:
    EVENT_LOGGER.info(event, extra={"fields": fields})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = (
            Headers(scope=scope).get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:REQUEST_ID_LENGTH]
        )
        request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            log_event(
                "request.done",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
