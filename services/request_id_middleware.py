from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from services.request_context import reset_request_id, set_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    HEADER_NAME = "X-Request-ID"
    ALT_HEADER_NAME = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = (
            request.headers.get(self.HEADER_NAME)
            or request.headers.get(self.ALT_HEADER_NAME)
            or str(uuid4())
        )

        token = set_request_id(request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)

        response.headers[self.HEADER_NAME] = request_id
        return response


def setup_request_id_middleware(app) -> None:
    app.add_middleware(RequestIDMiddleware)
