# routes_config.py

from fastapi import APIRouter

auth_router = APIRouter(tags=["Auth Routers"])
user_router = APIRouter(tags=["User Routers"])
document_router = APIRouter(tags=["Document Management"])
lecture_router = APIRouter(tags=["Lecture Generation"])


import auth.routes
import document.routes
import lecture.routes
import user.routes
