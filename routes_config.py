# routes_config.py

from fastapi import APIRouter, Depends

from utils.db import get_session

auth_router = APIRouter(
    dependencies=[Depends(get_session)],
    tags=["Auth Routers"],
)
user_router = APIRouter(dependencies=[Depends(get_session)], tags=["User Routers"])


import auth.routes
import user.routes

