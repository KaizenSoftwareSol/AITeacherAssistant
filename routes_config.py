# routes_config.py

from fastapi import APIRouter

auth_router = APIRouter(tags=["Auth Routers"])
user_router = APIRouter(tags=["User Routers"])
document_router = APIRouter(tags=["Document Management"])
lecture_router = APIRouter(tags=["Lecture Generation"])
course_router = APIRouter(tags=["Course Management"])
student_router = APIRouter(tags=["Student Portal"])
teacher_router = APIRouter(tags=["Teacher Resources"])
notification_router = APIRouter(tags=["Notifications"])
admin_router = APIRouter(tags=["Admin Management"])


import admin.routes
import auth.routes
import course.routes
import document.routes
import lecture.routes
import student.routes
import user.routes
import teacher.routes
import notification.routes
