import io
import csv
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from database import engine, Base, get_db
from models import User, Registration
from schemas import (
    RegistrationCreate,
    RegistrationResponse,
    RegistrationStatusUpdate,
    UserCreate,
    UserLogin,
    UserResponse,
    Token,
    DashboardStats,
)
from auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_admin_user,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create SQLite database tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Seed default admin user on startup if no admin exists
    db: Session = next(get_db())
    try:
        admin_count = db.query(User).filter(User.is_admin == True).count()
        if admin_count == 0:
            default_admin = User(
                username="admin",
                email="admin@miic.mz",
                hashed_password=get_password_hash("admin2026"),
                is_admin=True,
            )
            db.add(default_admin)
            db.commit()
            print("=" * 60)
            print("[MIIC Backend] Default admin account initialized:")
            print("       Username: admin")
            print("       Password: admin2026")
            print("=" * 60)
    finally:
        db.close()

    yield


app = FastAPI(
    title="MIIC 2026 — Event Registration API",
    description="Backend for event registrations and administration for MIIC 2026 (Mozambique International Investment Conference).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration to allow cross-origin requests from frontend (Vite/TanStack)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# Root & Health Check
# ==========================================

@app.get("/", tags=["General"])
def root():
    return {
        "app": "MIIC 2026 — Event Registration API",
        "status": "online",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/api/health", tags=["General"])
def health():
    return {"status": "ok"}


# ==========================================
# Admin Authentication
# ==========================================

@app.post("/api/auth/login", response_model=Token, tags=["Authentication"])
def login_json(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Admin login via JSON payload (username and password).
    Returns JWT access token.
    """
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required.",
        )

    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@app.post("/api/auth/token", response_model=Token, tags=["Authentication"])
def login_swagger_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    OAuth2 compatible token endpoint for Swagger UI Authorize button.
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin privileges required.",
        )

    access_token = create_access_token(data={"sub": user.username, "user_id": user.id})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_profile(current_user: User = Depends(get_current_admin_user)):
    """Returns currently authenticated admin user profile."""
    return current_user


@app.post("/api/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Admin Management"])
def create_admin_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Creates a new admin user (only existing authenticated admins can perform this).
    """
    existing_user = db.query(User).filter(
        or_(User.username == user_in.username, User.email == user_in.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username or email already exists.",
        )

    new_admin = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        is_admin=True,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin


# ==========================================
# Event Registrations (Public & Admin)
# ==========================================

@app.post("/api/registrations", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED, tags=["Registrations"])
@app.post("/api/inscricoes", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def register_attendee(payload: RegistrationCreate, db: Session = Depends(get_db)):
    """
    Public registration submission endpoint for the conference.
    Accepts attendee fields: full_name, email, phone, organization, country, participant_type, message.
    """
    # Prevent duplicate registration with the same email
    existing = db.query(Registration).filter(
        func.lower(Registration.email) == payload.email.lower()
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is already registered for MIIC 2026.",
        )

    new_reg = Registration(
        full_name=payload.full_name.strip(),
        email=payload.email.strip().lower(),
        phone=payload.phone.strip() if payload.phone else None,
        organization=payload.organization.strip() if payload.organization else None,
        country=payload.country.strip(),
        participant_type=payload.participant_type or "0",
        message=payload.message.strip() if payload.message else None,
        status="pending",
    )
    db.add(new_reg)
    db.commit()
    db.refresh(new_reg)
    return new_reg


@app.get("/api/registrations", response_model=List[RegistrationResponse], tags=["Registrations (Admin)"])
@app.get("/api/inscricoes", response_model=List[RegistrationResponse], include_in_schema=False)
def list_registrations(
    search: Optional[str] = Query(None, description="Search by name, email, organization, or country"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, confirmed, cancelled"),
    participant_type: Optional[str] = Query(None, alias="type", description="Filter by participant type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    List all event registrations with search, status filtering, and pagination.
    Protected: requires admin authentication.
    """
    query = db.query(Registration)

    if status_filter:
        query = query.filter(Registration.status == status_filter)

    if participant_type:
        query = query.filter(Registration.participant_type == participant_type)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Registration.full_name.ilike(search_term),
                Registration.email.ilike(search_term),
                Registration.organization.ilike(search_term),
                Registration.country.ilike(search_term),
            )
        )

    registrations = query.order_by(Registration.created_at.desc()).offset(skip).limit(limit).all()
    return registrations


@app.get("/api/registrations/{id}", response_model=RegistrationResponse, tags=["Registrations (Admin)"])
@app.get("/api/inscricoes/{id}", response_model=RegistrationResponse, include_in_schema=False)
def get_registration(
    id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get registration details by ID.
    Protected: requires admin authentication.
    """
    reg = db.query(Registration).filter(Registration.id == id).first()
    if not reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration with ID {id} was not found.",
        )
    return reg


@app.patch("/api/registrations/{id}/status", response_model=RegistrationResponse, tags=["Registrations (Admin)"])
@app.patch("/api/inscricoes/{id}/status", response_model=RegistrationResponse, include_in_schema=False)
def update_registration_status(
    id: int,
    status_data: RegistrationStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Update registration status (pending, confirmed, cancelled).
    Protected: requires admin authentication.
    """
    reg = db.query(Registration).filter(Registration.id == id).first()
    if not reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration with ID {id} was not found.",
        )

    # Normalize status values
    new_status = status_data.status.lower()
    if new_status in ["pendente", "pending"]:
        reg.status = "pending"
    elif new_status in ["confirmado", "confirmed"]:
        reg.status = "confirmed"
    elif new_status in ["cancelado", "cancelled"]:
        reg.status = "cancelled"
    else:
        reg.status = new_status

    db.commit()
    db.refresh(reg)
    return reg


@app.delete("/api/registrations/{id}", tags=["Registrations (Admin)"])
@app.delete("/api/inscricoes/{id}", include_in_schema=False)
def delete_registration(
    id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Permanently delete a registration record from the system.
    Protected: requires admin authentication.
    """
    reg = db.query(Registration).filter(Registration.id == id).first()
    if not reg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Registration with ID {id} was not found.",
        )

    deleted_name = reg.full_name
    db.delete(reg)
    db.commit()

    return {
        "success": True,
        "message": f"Registration for '{deleted_name}' (ID: {id}) was successfully deleted.",
        "id": id,
    }


# ==========================================
# Statistics & CSV Export
# ==========================================

@app.get("/api/admin/stats", response_model=DashboardStats, tags=["Analytics (Admin)"])
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Aggregated dashboard analytics for registrations.
    Protected: requires admin authentication.
    """
    total = db.query(Registration).count()
    pending = db.query(Registration).filter(
        or_(Registration.status == "pending", Registration.status == "pendente")
    ).count()
    confirmed = db.query(Registration).filter(
        or_(Registration.status == "confirmed", Registration.status == "confirmado")
    ).count()
    cancelled = db.query(Registration).filter(
        or_(Registration.status == "cancelled", Registration.status == "cancelado")
    ).count()

    # Top countries
    country_counts = (
        db.query(Registration.country, func.count(Registration.id))
        .group_by(Registration.country)
        .order_by(func.count(Registration.id).desc())
        .limit(10)
        .all()
    )
    by_country = {c: count for c, count in country_counts if c}

    # Participant types
    type_counts = (
        db.query(Registration.participant_type, func.count(Registration.id))
        .group_by(Registration.participant_type)
        .all()
    )
    by_type = {t: count for t, count in type_counts if t}

    return {
        "total_registrations": total,
        "pending": pending,
        "confirmed": confirmed,
        "cancelled": cancelled,
        "by_country": by_country,
        "by_type": by_type,
    }


@app.get("/api/registrations/export/csv", tags=["Analytics (Admin)"])
@app.get("/api/inscricoes/export/csv", include_in_schema=False)
def export_registrations_csv(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Export all event registrations as a downloadable CSV file.
    Protected: requires admin authentication.
    """
    registrations = db.query(Registration).order_by(Registration.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID",
        "Full Name",
        "Email",
        "Phone",
        "Organization",
        "Country",
        "Participant Type",
        "Message",
        "Status",
        "Registration Date"
    ])

    for reg in registrations:
        writer.writerow([
            reg.id,
            reg.full_name,
            reg.email,
            reg.phone or "",
            reg.organization or "",
            reg.country,
            reg.participant_type,
            (reg.message or "").replace("\n", " "),
            reg.status,
            reg.created_at.strftime("%Y-%m-%d %H:%M:%S") if reg.created_at else ""
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=miic_2026_registrations.csv"}
    )
