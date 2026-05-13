# services/activity_log_middleware.py
#
# Centralized activity logging middleware.
# Intercepts specific routes after a successful (2xx) response and fires an
# asyncio background task that writes one row to teacher_activity_log.
# Errors are always swallowed so logging never affects the response.

import asyncio
import json
import re
from typing import Optional

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from logger import logger
from services.activity_log_service import ActivityLogService
from settings import settings
from utils.db import db as _db

# ---------------------------------------------------------------------------
# Path patterns  (matched after stripping any /api/v1 root_path prefix)
# ---------------------------------------------------------------------------

# Teacher routes
_RE_LOGIN             = re.compile(r"^/auth/login$")
_RE_GENERATE          = re.compile(r"^/lectures/generate$")
_RE_GENERATE_FILES    = re.compile(r"^/lectures/generate-with-files$")
_RE_DELETE_LECTURE    = re.compile(r"^/lectures/([^/]+)$")
_RE_PUBLISH           = re.compile(r"^/lectures/([^/]+)/publish$")
_RE_GEN_SUMMARY       = re.compile(r"^/lectures/([^/]+)/generate-summary$")
_RE_GEN_QUIZ          = re.compile(r"^/lectures/([^/]+)/generate-quiz$")
_RE_GEN_FLASHCARDS    = re.compile(r"^/lectures/([^/]+)/generate-flashcards$")

# Student routes
_RE_STUDENT_ASSESSMENT_SUBMIT = re.compile(r"^/student/assessments/([^/]+)/submit$")
_RE_STUDENT_QUIZ_SUBMIT       = re.compile(r"^/student/test-quizzes/([^/]+)/submit$")
_RE_STUDENT_CHAT              = re.compile(r"^/student/lectures/([^/]+)/chat$")
_RE_STUDENT_DOWNLOAD          = re.compile(r"^/lectures/([^/]+)/download$")
_RE_STUDENT_GEN_QUIZ          = re.compile(r"^/student/lectures/([^/]+)/generate-quiz$")

_ROOT_PATH_PREFIX = "/api/v1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_path(path: str) -> str:
    if path.startswith(_ROOT_PATH_PREFIX):
        return path[len(_ROOT_PATH_PREFIX):]
    return path


def _is_loggable(method: str, path: str) -> bool:
    # Teacher
    if method == "POST" and _RE_LOGIN.match(path):
        return True
    if method == "POST" and (_RE_GENERATE.match(path) or _RE_GENERATE_FILES.match(path)):
        return True
    if method == "DELETE" and _RE_DELETE_LECTURE.match(path):
        return True
    if method == "PATCH" and _RE_PUBLISH.match(path):
        return True
    if method == "POST" and (
        _RE_GEN_SUMMARY.match(path) or _RE_GEN_QUIZ.match(path) or _RE_GEN_FLASHCARDS.match(path)
    ):
        return True
    # Student
    if method == "POST" and (
        _RE_STUDENT_ASSESSMENT_SUBMIT.match(path)
        or _RE_STUDENT_QUIZ_SUBMIT.match(path)
        or _RE_STUDENT_CHAT.match(path)
        or _RE_STUDENT_GEN_QUIZ.match(path)
    ):
        return True
    if method == "GET" and _RE_STUDENT_DOWNLOAD.match(path):
        return True
    return False


def _bearer_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Async DB helpers
# ---------------------------------------------------------------------------

async def _user_from_uuid(uuid_str: str) -> Optional[dict]:
    """Return {user_id, role, university_id} for a user UUID."""
    try:
        data = _db.get_user_by_id(uuid_str)
        if data:
            return {
                "user_id": data["id"],
                "role": str(data.get("role", "")).upper(),
                "university_id": data.get("university_id"),
            }
    except Exception as exc:
        logger.debug(f"[ActivityLog] _user_from_uuid failed: {exc}")
    return None


async def _teacher_id(user_id: int) -> Optional[int]:
    try:
        res = _db.get_admin_client().table("teacher").select("id").eq("user_id", user_id).limit(1).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.debug(f"[ActivityLog] _teacher_id failed: {exc}")
        return None


async def _student_id(user_id: int) -> Optional[int]:
    try:
        res = _db.get_admin_client().table("student").select("id").eq("user_id", user_id).limit(1).execute()
        return res.data[0]["id"] if res.data else None
    except Exception as exc:
        logger.debug(f"[ActivityLog] _student_id failed: {exc}")
        return None


async def _lecture_info(lecture_uuid: str) -> Optional[dict]:
    """Return {int_id, title} for a lecture UUID."""
    try:
        res = _db.get_admin_client().table("lecture").select("id,title").eq("uuid", lecture_uuid).limit(1).execute()
        if res.data:
            return {"int_id": res.data[0]["id"], "title": res.data[0].get("title", "")}
    except Exception as exc:
        logger.debug(f"[ActivityLog] _lecture_info failed: {exc}")
    return None


async def _assessment_info(assessment_uuid: str) -> Optional[dict]:
    """Return {int_id, title} for an assessment UUID."""
    try:
        res = _db.get_admin_client().table("assessment").select("id,title").eq("uuid", assessment_uuid).limit(1).execute()
        if res.data:
            return {"int_id": res.data[0]["id"], "title": res.data[0].get("title", "")}
    except Exception as exc:
        logger.debug(f"[ActivityLog] _assessment_info failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# Background logging coroutine
# ---------------------------------------------------------------------------

async def _log_async(
    method: str,
    path: str,
    auth_token: Optional[str],
    response_body: Optional[bytes],
    pre_data: dict,
) -> None:
    try:
        # ---- LOGIN (teacher OR student) ------------------------------------
        if method == "POST" and _RE_LOGIN.match(path):
            if not response_body:
                return
            try:
                resp = json.loads(response_body)
                token = resp.get("access_token")
                if not token:
                    return
            except (json.JSONDecodeError, TypeError):
                return

            payload = _decode_jwt(token)
            if not payload:
                return
            sub = payload.get("sub")
            if not sub:
                return
            user_info = await _user_from_uuid(sub)
            if not user_info:
                return

            role = user_info["role"]
            uid = user_info["user_id"]
            univ = user_info["university_id"]

            if role == "TEACHER":
                tid = await _teacher_id(uid)
                ActivityLogService.log_login(_db, user_id=uid, teacher_id=tid, university_id=univ)
            elif role == "STUDENT":
                sid = await _student_id(uid)
                ActivityLogService.log_student_login(_db, user_id=uid, student_id=sid, university_id=univ)
            return

        # ---- All other endpoints need a valid JWT -------------------------
        if not auth_token:
            return
        payload = _decode_jwt(auth_token)
        if not payload:
            return
        sub = payload.get("sub")
        if not sub:
            return
        user_info = await _user_from_uuid(sub)
        if not user_info:
            return

        uid = user_info["user_id"]
        role = user_info["role"]
        univ = user_info["university_id"]

        # ---- TEACHER routes -----------------------------------------------

        if role == "TEACHER":
            tid = await _teacher_id(uid)

            # GENERATE LECTURE
            if method == "POST" and (_RE_GENERATE.match(path) or _RE_GENERATE_FILES.match(path)):
                if not response_body:
                    return
                try:
                    resp = json.loads(response_body)
                except (json.JSONDecodeError, TypeError):
                    return
                lec = await _lecture_info(resp.get("lecture_id", ""))
                ActivityLogService.log_generate_lecture(
                    _db, user_id=uid, teacher_id=tid, university_id=univ,
                    lecture_id=lec["int_id"] if lec else None,
                    lecture_name=resp.get("title", ""),
                )
                return

            # DELETE LECTURE
            if method == "DELETE" and _RE_DELETE_LECTURE.match(path):
                ActivityLogService.log_delete_lecture(
                    _db, user_id=uid, teacher_id=tid, university_id=univ,
                    lecture_id=pre_data.get("lecture_int_id"),
                    lecture_name=pre_data.get("lecture_title", ""),
                )
                return

            # PUBLISH LECTURE
            m = _RE_PUBLISH.match(path)
            if method == "PATCH" and m:
                lec = await _lecture_info(m.group(1))
                ActivityLogService.log_publish_lecture(
                    _db, user_id=uid, teacher_id=tid, university_id=univ,
                    lecture_id=lec["int_id"] if lec else None,
                    lecture_name=lec["title"] if lec else "",
                )
                return

            # GENERATE LEARNING MATERIALS
            for pattern, material_type in (
                (_RE_GEN_SUMMARY,    "summary"),
                (_RE_GEN_QUIZ,       "quiz"),
                (_RE_GEN_FLASHCARDS, "flashcards"),
            ):
                m = pattern.match(path)
                if method == "POST" and m:
                    lec = await _lecture_info(m.group(1))
                    ActivityLogService.log_generate_learning_materials(
                        _db, user_id=uid, teacher_id=tid, university_id=univ,
                        lecture_id=lec["int_id"] if lec else None,
                        lecture_name=lec["title"] if lec else "",
                        material_type=material_type,
                    )
                    return

        # ---- STUDENT routes -----------------------------------------------

        if role == "STUDENT":
            sid = await _student_id(uid)

            # TAKE ASSESSMENT
            m = _RE_STUDENT_ASSESSMENT_SUBMIT.match(path)
            if method == "POST" and m:
                asmt = await _assessment_info(m.group(1))
                ActivityLogService.log_student_take_assessment(
                    _db, user_id=uid, student_id=sid, university_id=univ,
                    assessment_id=asmt["int_id"] if asmt else None,
                    assessment_name=asmt["title"] if asmt else "",
                )
                return

            # TAKE PRACTICE QUIZ (test-quiz submit)
            m = _RE_STUDENT_QUIZ_SUBMIT.match(path)
            if method == "POST" and m:
                asmt = await _assessment_info(m.group(1))
                ActivityLogService.log_student_take_quiz(
                    _db, user_id=uid, student_id=sid, university_id=univ,
                    assessment_id=asmt["int_id"] if asmt else None,
                    assessment_name=asmt["title"] if asmt else "",
                )
                return

            # CHAT MESSAGE
            m = _RE_STUDENT_CHAT.match(path)
            if method == "POST" and m:
                lec = await _lecture_info(m.group(1))
                ActivityLogService.log_student_chat(
                    _db, user_id=uid, student_id=sid, university_id=univ,
                    lecture_id=lec["int_id"] if lec else None,
                    lecture_name=lec["title"] if lec else "",
                )
                return

            # DOWNLOAD LECTURE
            m = _RE_STUDENT_DOWNLOAD.match(path)
            if method == "GET" and m:
                lec = await _lecture_info(m.group(1))
                ActivityLogService.log_student_download(
                    _db, user_id=uid, student_id=sid, university_id=univ,
                    lecture_id=lec["int_id"] if lec else None,
                    lecture_name=lec["title"] if lec else "",
                )
                return

            # GENERATE PRACTICE QUIZ (student-side quiz gen)
            m = _RE_STUDENT_GEN_QUIZ.match(path)
            if method == "POST" and m:
                lec = await _lecture_info(m.group(1))
                ActivityLogService.log_student_generate_quiz(
                    _db, user_id=uid, student_id=sid, university_id=univ,
                    lecture_id=lec["int_id"] if lec else None,
                    lecture_name=lec["title"] if lec else "",
                )
                return

    except Exception as exc:
        logger.warning(f"[ActivityLog] Unhandled error in background task: {exc}")


# ---------------------------------------------------------------------------
# Middleware class
# ---------------------------------------------------------------------------

class ActivityLogMiddleware(BaseHTTPMiddleware):
    """
    Fire-and-forget activity logging for teacher and student actions.

    Teacher hooks: POST /auth/login, POST /lectures/generate,
        POST /lectures/generate-with-files, DELETE /lectures/{id},
        PATCH /lectures/{id}/publish,
        POST /lectures/{id}/generate-summary|quiz|flashcards

    Student hooks: POST /auth/login (student role),
        POST /student/assessments/{id}/submit,
        POST /student/test-quizzes/{id}/submit,
        POST /student/lectures/{id}/chat,
        GET  /lectures/{id}/download (student role),
        POST /student/lectures/{id}/generate-quiz
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = _normalize_path(request.url.path)

        if not _is_loggable(method, path):
            return await call_next(request)

        # Pre-request: capture lecture info BEFORE DELETE destroys it
        pre_data: dict = {}
        m = _RE_DELETE_LECTURE.match(path)
        if method == "DELETE" and m:
            try:
                lec = await _lecture_info(m.group(1))
                if lec:
                    pre_data["lecture_int_id"] = lec["int_id"]
                    pre_data["lecture_title"] = lec["title"]
            except Exception:
                pass

        response = await call_next(request)

        # Only log successful responses
        if not (200 <= response.status_code < 300):
            return response

        # Buffer response body only for endpoints that need it
        needs_body = method == "POST" and (
            _RE_LOGIN.match(path)
            or _RE_GENERATE.match(path)
            or _RE_GENERATE_FILES.match(path)
        )

        response_body: Optional[bytes] = None
        if needs_body:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            response_body = b"".join(chunks)
            response = Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        auth_token = _bearer_token(request)

        asyncio.create_task(
            _log_async(method, path, auth_token, response_body, pre_data)
        )

        return response
