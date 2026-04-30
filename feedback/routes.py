from datetime import datetime
import re
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from dependencies import AnyUser, SystemUser
from logger import logger
from models.feedback import (
    FeedbackCreate,
    FeedbackDifficultyLevel,
    FeedbackFeatureArea,
    FeedbackListResponse,
    FeedbackResponseCreate,
    FeedbackStatus,
    FeedbackStatusUpdate,
    FeedbackUpdate,
    map_feedback_record,
)
from models.user import UserRole
from settings import settings
from supabase_config import supabase
from utils.db import get_db

router = APIRouter()
system_feedback_router = APIRouter()

FEEDBACK_BUCKET = "feedback-attachments"
MAX_ATTACHMENTS = 3
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _user_full_name(user: dict) -> str:
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    full_name = f"{first} {last}".strip()
    return full_name or user.get("username") or user.get("email") or "Unknown user"


def _ensure_feedback_user(user_role: UserRole) -> None:
    if user_role not in [UserRole.STUDENT, UserRole.TEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feedback is available only to student and teacher users",
        )


def _validate_feedback_status_for_response(status_value: FeedbackStatus) -> None:
    if status_value not in [FeedbackStatus.RESPONDED, FeedbackStatus.CLOSED, FeedbackStatus.IN_REVIEW]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response status must be RESPONDED, IN_REVIEW, or CLOSED",
        )


def _sanitize_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._")
    return safe or "upload.png"


async def _upload_attachments(
    user_uuid: str,
    feedback_uuid: str,
    files: list[UploadFile],
) -> list[dict]:
    if len(files) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_ATTACHMENTS} screenshots are allowed",
        )

    uploaded = []
    for file in files:
        if not file.filename:
            continue
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported image type: {file.content_type}",
            )

        file_data = await file.read()
        await file.seek(0)
        if len(file_data) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image {file.filename} exceeds 5MB limit",
            )

        safe_filename = _sanitize_filename(file.filename)
        file_key = f"{uuid4()}-{safe_filename}"
        path = f"feedback/{user_uuid}/{feedback_uuid}/{file_key}"
        supabase.upload_file(
            FEEDBACK_BUCKET,
            path,
            file_data,
            {"content-type": file.content_type, "upsert": "false"},
        )
        public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/{FEEDBACK_BUCKET}/{path}"
        uploaded.append(
            {
                "url": public_url,
                "path": path,
                "filename": file.filename,
                "mimeType": file.content_type,
                "size": len(file_data),
            }
        )

    return uploaded


def _get_next_feedback_id(db) -> int:
    latest = (
        db.admin_client.table("feedback")
        .select("id")
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if latest.data and len(latest.data) > 0:
        return int(latest.data[0]["id"]) + 1
    return 1


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_feedback(
    current_user: AnyUser,
    feature_area: FeedbackFeatureArea = Form(...),
    difficulty_level: FeedbackDifficultyLevel = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    screenshots: list[UploadFile] = File(default=[]),
    db=Depends(get_db),
):
    _ensure_feedback_user(current_user.role)

    payload = FeedbackCreate(
        feature_area=feature_area,
        difficulty_level=difficulty_level,
        title=title,
        description=description,
    )

    feedback_uuid = str(uuid4())
    user_uuid = str(current_user.uuid or current_user.id)
    attachments = await _upload_attachments(user_uuid=user_uuid, feedback_uuid=feedback_uuid, files=screenshots)

    record = {
        "id": _get_next_feedback_id(db),
        "uuid": feedback_uuid,
        "user_id": int(current_user.id),
        "user_role": current_user.role.value,
        "feature_area": payload.feature_area.value,
        "difficulty_level": payload.difficulty_level.value,
        "title": payload.title,
        "description": payload.description,
        "attachments": attachments,
        "status": FeedbackStatus.OPEN.value,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    result = db.admin_client.table("feedback").insert(record).execute()
    created = result.data[0] if result.data else record
    user_name = _user_full_name(current_user.model_dump() if hasattr(current_user, "model_dump") else dict(current_user))
    return map_feedback_record(created, user_name=user_name)


@router.get("/me", response_model=FeedbackListResponse)
async def get_my_feedback(
    current_user: AnyUser,
    page: int = Query(1, ge=1),
    items_per_page: int = Query(20, ge=1, le=100),
    status_filter: FeedbackStatus | None = Query(None, alias="status"),
    db=Depends(get_db),
):
    _ensure_feedback_user(current_user.role)
    offset = (page - 1) * items_per_page

    query = (
        db.admin_client.table("feedback")
        .select("*", count="exact")
        .eq("user_id", int(current_user.id))
        .order("created_at", desc=True)
    )
    if status_filter:
        query = query.eq("status", status_filter.value)

    result = query.range(offset, offset + items_per_page - 1).execute()
    records = result.data or []
    user_name = _user_full_name(current_user.model_dump() if hasattr(current_user, "model_dump") else dict(current_user))
    items = [map_feedback_record(r, user_name=user_name) for r in records]
    return FeedbackListResponse(items=items, total=result.count or 0, page=page, itemsPerPage=items_per_page)


@router.get("/{feedback_id}")
async def get_feedback_detail(
    feedback_id: str,
    current_user: AnyUser,
    db=Depends(get_db),
):
    query = db.admin_client.table("feedback").select("*").eq("uuid", feedback_id)
    if current_user.role != UserRole.SYSTEM:
        query = query.eq("user_id", int(current_user.id))
    result = query.execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    record = result.data[0]
    submitter = db.get_user_by_id(record["user_id"], use_cache=False) or {}
    responder = (
        db.get_user_by_id(record.get("responded_by_user_id"), use_cache=False)
        if record.get("responded_by_user_id")
        else {}
    )
    return map_feedback_record(
        record,
        user_name=_user_full_name(submitter),
        responder_name=_user_full_name(responder) if responder else "",
    )


@router.patch("/{feedback_id}")
async def update_feedback(
    feedback_id: str,
    payload: FeedbackUpdate,
    current_user: AnyUser,
    db=Depends(get_db),
):
    _ensure_feedback_user(current_user.role)
    existing = (
        db.admin_client.table("feedback")
        .select("*")
        .eq("uuid", feedback_id)
        .eq("user_id", int(current_user.id))
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    record = existing.data[0]
    if record.get("status") != FeedbackStatus.OPEN.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only OPEN feedback can be edited",
        )

    update_data = payload.model_dump(exclude_none=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()
    result = db.admin_client.table("feedback").update(update_data).eq("uuid", feedback_id).execute()
    updated = result.data[0] if result.data else record
    return map_feedback_record(updated, user_name=_user_full_name(current_user.model_dump()))


@system_feedback_router.get("/list", response_model=FeedbackListResponse)
async def list_feedback_for_system(
    current_user: SystemUser,
    page: int = Query(1, ge=1),
    items_per_page: int = Query(20, ge=1, le=100),
    status_filter: FeedbackStatus | None = Query(None, alias="status"),
    feature_area: FeedbackFeatureArea | None = None,
    db=Depends(get_db),
):
    offset = (page - 1) * items_per_page
    query = db.admin_client.table("feedback").select("*", count="exact").order("created_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter.value)
    if feature_area:
        query = query.eq("feature_area", feature_area.value)

    result = query.range(offset, offset + items_per_page - 1).execute()
    records = result.data or []
    user_ids = list({r.get("user_id") for r in records if r.get("user_id")})
    responder_ids = list({r.get("responded_by_user_id") for r in records if r.get("responded_by_user_id")})
    users = {}
    for uid in user_ids + responder_ids:
        if uid and uid not in users:
            users[uid] = db.get_user_by_id(uid, use_cache=False) or {}

    items = []
    for record in records:
        submitter = users.get(record.get("user_id"), {})
        responder = users.get(record.get("responded_by_user_id"), {})
        items.append(
            map_feedback_record(
                record,
                user_name=_user_full_name(submitter),
                responder_name=_user_full_name(responder) if responder else "",
            )
        )
    return FeedbackListResponse(items=items, total=result.count or 0, page=page, itemsPerPage=items_per_page)


@system_feedback_router.post("/{feedback_id}/response")
async def respond_feedback(
    feedback_id: str,
    payload: FeedbackResponseCreate,
    current_user: SystemUser,
    db=Depends(get_db),
):
    _validate_feedback_status_for_response(payload.status)
    existing = db.admin_client.table("feedback").select("*").eq("uuid", feedback_id).execute()
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    update_data = {
        "system_response": payload.response,
        "status": payload.status.value,
        "responded_by_user_id": int(current_user.id),
        "responded_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    result = db.admin_client.table("feedback").update(update_data).eq("uuid", feedback_id).execute()
    updated = result.data[0] if result.data else existing.data[0]
    submitter = db.get_user_by_id(updated["user_id"], use_cache=False) or {}
    return map_feedback_record(
        updated,
        user_name=_user_full_name(submitter),
        responder_name=_user_full_name(current_user.model_dump()),
    )


@system_feedback_router.patch("/{feedback_id}/status")
async def update_feedback_status(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    current_user: SystemUser,
    db=Depends(get_db),
):
    _ = current_user
    existing = db.admin_client.table("feedback").select("*").eq("uuid", feedback_id).execute()
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
    update_data = {
        "status": payload.status.value,
        "updated_at": datetime.utcnow().isoformat(),
    }
    result = db.admin_client.table("feedback").update(update_data).eq("uuid", feedback_id).execute()
    updated = result.data[0] if result.data else existing.data[0]
    submitter = db.get_user_by_id(updated["user_id"], use_cache=False) or {}
    return map_feedback_record(updated, user_name=_user_full_name(submitter))


from routes_config import feedback_router as main_feedback_router
from routes_config import system_router as main_system_router

main_feedback_router.include_router(router)
main_system_router.include_router(system_feedback_router, prefix="/feedback", tags=["System Feedback"])
