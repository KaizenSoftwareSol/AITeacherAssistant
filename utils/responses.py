# utils/responses.py

from typing import Any, Dict, Optional

from fastapi import status
from fastapi.responses import JSONResponse


def success_response(
    data: Any = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
) -> JSONResponse:
    """
    Create a standardized success response
    """
    response_data = {
        "status": "success",
        "message": message,
        "data": data,
    }
    return JSONResponse(content=response_data, status_code=status_code)


def error_response(
    message: str = "An error occurred",
    status_code: int = status.HTTP_400_BAD_REQUEST,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a standardized error response
    """
    response_data = {
        "status": "error",
        "message": message,
        "details": details,
    }
    return JSONResponse(content=response_data, status_code=status_code)
