# utils/db.py

from sqlmodel import Session, SQLModel, create_engine, select

from auth.models import User
from settings import settings

engine = create_engine(
    settings.SQLITE_DATABASE_URL,
    echo=False,  # Logs generated SQL queries; set False in production
)


def get_session():
    """FastAPI Dependency to get DB session."""
    with Session(engine) as session:
        yield session


async def create_db_and_tables():
    """Create database tables if they don't exist and initialize admin user if no users exist."""
    SQLModel.metadata.create_all(engine)

    # Create admin user if no users exist
    with Session(engine) as session:
        user_exists = session.exec(select(User)).first()
        if not user_exists:
            from auth.models import UserCreate, UserRole
            from auth.service import AuthService

            # Create admin user
            admin_user = UserCreate(
                email="admin@admin.com",
                username="admin",
                password="123",
                role=UserRole.ADMIN,
            )

            await AuthService.create_user(session, admin_user)
            session.commit()

