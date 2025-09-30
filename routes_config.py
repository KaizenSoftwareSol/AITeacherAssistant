# routes_config.py

from fastapi import APIRouter

auth_router = APIRouter(tags=["Auth Routers"])
user_router = APIRouter(tags=["User Routers"])
document_router = APIRouter(tags=["Document Management"])


import auth.routes
import user.routes
import document.routes

