# routes_config.py

from fastapi import APIRouter

auth_router = APIRouter(tags=["Auth Routers"])
user_router = APIRouter(tags=["User Routers"])
document_router = APIRouter(tags=["Document Management"])
lecture_router = APIRouter(tags=["Lecture Generation"])
course_router = APIRouter(tags=["Course Management"])


import auth.routes
import course.routes
import document.routes
import lecture.routes
import user.routes
