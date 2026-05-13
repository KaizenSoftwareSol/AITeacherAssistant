# services/activity_log_service.py
#
# Fire-and-forget activity logger for both teacher and student actions.
# Every public method swallows exceptions so a logging failure never breaks
# the calling endpoint.

from datetime import datetime, timezone
from typing import Optional

from logger import logger


class ActivityLogService:
    """Logs teacher and student actions to the teacher_activity_log table."""

    # ---- Teacher activity type constants -----------------------------------
    LOGIN                       = "LOGIN"
    GENERATE_LECTURE            = "GENERATE_LECTURE"
    GENERATE_LEARNING_MATERIALS = "GENERATE_LEARNING_MATERIALS"
    DELETE_LECTURE              = "DELETE_LECTURE"
    PUBLISH_LECTURE             = "PUBLISH_LECTURE"

    # ---- Student activity type constants -----------------------------------
    STUDENT_LOGIN          = "STUDENT_LOGIN"
    STUDENT_TAKE_ASSESSMENT = "STUDENT_TAKE_ASSESSMENT"
    STUDENT_TAKE_QUIZ      = "STUDENT_TAKE_QUIZ"
    STUDENT_CHAT           = "STUDENT_CHAT"
    STUDENT_DOWNLOAD       = "STUDENT_DOWNLOAD"
    STUDENT_GENERATE_QUIZ  = "STUDENT_GENERATE_QUIZ"

    # Sets for quick type-membership checks
    TEACHER_TYPES = frozenset({LOGIN, GENERATE_LECTURE, GENERATE_LEARNING_MATERIALS, DELETE_LECTURE, PUBLISH_LECTURE})
    STUDENT_TYPES = frozenset({STUDENT_LOGIN, STUDENT_TAKE_ASSESSMENT, STUDENT_TAKE_QUIZ, STUDENT_CHAT, STUDENT_DOWNLOAD, STUDENT_GENERATE_QUIZ})

    @staticmethod
    def _insert(db, record: dict) -> None:
        """Raw insert using the admin client (bypasses RLS)."""
        db.get_admin_client().table("teacher_activity_log").insert(record).execute()

    @staticmethod
    def log(
        db,
        activity_type: str,
        user_id: Optional[int] = None,
        teacher_id: Optional[int] = None,
        student_id: Optional[int] = None,
        university_id: Optional[int] = None,
        lecture_id: Optional[int] = None,
        lecture_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Insert one activity log entry. Silently ignores all errors."""
        try:
            record: dict = {
                "activity_type": activity_type,
                "user_id": user_id,
                "teacher_id": teacher_id,
                "university_id": university_id,
                "lecture_id": lecture_id,
                "lecture_name": lecture_name,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Only include student_id when it has a value so teacher inserts
            # succeed even before the add_student_activity_log migration is run.
            if student_id is not None:
                record["student_id"] = student_id
            ActivityLogService._insert(db, record)
        except Exception as exc:
            logger.warning(f"[ActivityLog] Failed to log {activity_type}: {exc}")

    # ---- Teacher convenience wrappers --------------------------------------

    @staticmethod
    def log_login(db, user_id: int, teacher_id: Optional[int], university_id: Optional[int]) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.LOGIN,
            user_id=user_id,
            teacher_id=teacher_id,
            university_id=university_id,
        )

    @staticmethod
    def log_generate_lecture(
        db,
        user_id: int,
        teacher_id: int,
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.GENERATE_LECTURE,
            user_id=user_id,
            teacher_id=teacher_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )

    @staticmethod
    def log_generate_learning_materials(
        db,
        user_id: int,
        teacher_id: int,
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
        material_type: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.GENERATE_LEARNING_MATERIALS,
            user_id=user_id,
            teacher_id=teacher_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
            metadata={"material_type": material_type},
        )

    @staticmethod
    def log_delete_lecture(
        db,
        user_id: int,
        teacher_id: int,
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.DELETE_LECTURE,
            user_id=user_id,
            teacher_id=teacher_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )

    @staticmethod
    def log_publish_lecture(
        db,
        user_id: int,
        teacher_id: int,
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.PUBLISH_LECTURE,
            user_id=user_id,
            teacher_id=teacher_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )

    # ---- Student convenience wrappers --------------------------------------

    @staticmethod
    def log_student_login(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_LOGIN,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
        )

    @staticmethod
    def log_student_take_assessment(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
        assessment_id: Optional[int],
        assessment_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_TAKE_ASSESSMENT,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
            lecture_id=assessment_id,
            lecture_name=assessment_name,
        )

    @staticmethod
    def log_student_take_quiz(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
        assessment_id: Optional[int],
        assessment_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_TAKE_QUIZ,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
            lecture_id=assessment_id,
            lecture_name=assessment_name,
        )

    @staticmethod
    def log_student_chat(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_CHAT,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )

    @staticmethod
    def log_student_download(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_DOWNLOAD,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )

    @staticmethod
    def log_student_generate_quiz(
        db,
        user_id: int,
        student_id: Optional[int],
        university_id: Optional[int],
        lecture_id: Optional[int],
        lecture_name: str,
    ) -> None:
        ActivityLogService.log(
            db,
            activity_type=ActivityLogService.STUDENT_GENERATE_QUIZ,
            user_id=user_id,
            student_id=student_id,
            university_id=university_id,
            lecture_id=lecture_id,
            lecture_name=lecture_name,
        )
