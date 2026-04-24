from contextvars import ContextVar, Token
from typing import Optional


_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> Token:
    return _request_id_ctx.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id_ctx.get()


def reset_request_id(token: Token) -> None:
    _request_id_ctx.reset(token)
