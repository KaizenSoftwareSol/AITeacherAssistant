# utils/db.py

from sqlmodel import Session, SQLModel, create_engine, select
from supabase import create_client, Client

from models.user import User
from settings import settings

# Create Supabase client (only if environment variables are set)
supabase: Client = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
    try:
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        print("✓ Supabase client initialized successfully")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize Supabase client: {e}")
        print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")
else:
    print("⚠️  Warning: Supabase environment variables not set")
    print("   Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables")

# Create SQLModel engine for Supabase PostgreSQL (only if DATABASE_URL is set)
engine = None
if settings.DATABASE_URL:
    try:
        engine = create_engine(
            settings.DATABASE_URL,
            echo=False,  # Logs generated SQL queries; set False in production
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=300,  # Recycle connections every 5 minutes
        )
        print("✓ Database engine initialized successfully")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize database engine: {e}")
        print("   Please set DATABASE_URL environment variable")
else:
    print("⚠️  Warning: DATABASE_URL not set")
    print("   Please set DATABASE_URL environment variable")


def get_session():
    """FastAPI Dependency to get DB session."""
    if engine is None:
        raise RuntimeError("Database engine not initialized. Please set DATABASE_URL environment variable.")
    with Session(engine) as session:
        yield session


async def create_db_and_tables():
    """Create database tables if they don't exist and initialize admin user if no users exist."""
    if engine is None:
        print("⚠️  Warning: Database engine not initialized. Cannot create tables.")
        print("   Please set DATABASE_URL environment variable and restart the application.")
        return
    
    try:
        # Create all tables in Supabase
        SQLModel.metadata.create_all(engine)
        print("✓ Database tables created successfully in Supabase")
    except Exception as e:
        print(f"⚠️  Warning: Could not create tables automatically: {e}")
        print("   Please create tables manually in Supabase dashboard or run migrations")

    # Create admin user if no users exist
    try:
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

                # Create the actual User object with required fields
                hashed_password = AuthService.get_password_hash(admin_user.password)
                user = User(
                    email=admin_user.email,
                    username=admin_user.username,
                    hashed_password=hashed_password,
                    role=admin_user.role,
                    first_name="Admin",
                    last_name="User",
                    is_active=True
                )

                session.add(user)
                session.commit()
                print("✓ Admin user created successfully")
            else:
                print("✓ Admin user already exists")
    except Exception as e:
        print(f"⚠️  Warning: Could not create admin user: {e}")
        print("   Please create admin user manually in Supabase dashboard")

