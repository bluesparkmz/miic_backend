import io
import csv
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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


PROFILE_LABELS = {
    "0": "Investidor",
    "1": "Empresa",
    "2": "Governo / Instituição",
    "3": "Imprensa / Média",
    "4": "Outro",
}

STATUS_LABELS = {
    "pending": "Pendente",
    "confirmed": "Confirmada",
    "cancelled": "Cancelada",
}


@app.get("/api/registrations/export/csv", tags=["Analytics (Admin)"])
@app.get("/api/inscricoes/export/csv", include_in_schema=False)
def export_registrations_csv(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Export event registrations as a downloadable CSV file (with UTF-8 BOM for Microsoft Excel).
    Protected: requires admin authentication.
    """
    query = db.query(Registration)
    if status_filter and status_filter != "all":
        query = query.filter(Registration.status == status_filter)
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

    registrations = query.order_by(Registration.created_at.desc()).all()

    output = io.StringIO()
    # Write UTF-8 BOM for Microsoft Excel compatibility
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "ID",
        "Nome Completo",
        "Email",
        "Telefone",
        "Organização",
        "País",
        "Perfil",
        "Mensagem / Foco",
        "Status",
        "Data de Inscrição"
    ])

    for reg in registrations:
        profile_label = PROFILE_LABELS.get(reg.participant_type, reg.participant_type or "Outro")
        status_label = STATUS_LABELS.get(reg.status, reg.status)
        writer.writerow([
            reg.id,
            reg.full_name,
            reg.email,
            reg.phone or "",
            reg.organization or "",
            reg.country,
            profile_label,
            (reg.message or "").replace("\n", " "),
            status_label,
            reg.created_at.strftime("%d/%m/%Y %H:%M") if reg.created_at else ""
        ])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=inscricoes_miic_2026.csv"}
    )


@app.get("/api/registrations/export/pdf", tags=["Analytics (Admin)"])
@app.get("/api/inscricoes/export/pdf", include_in_schema=False)
def export_registrations_pdf(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Export event registrations as a formatted PDF report.
    Protected: requires admin authentication.
    """
    query = db.query(Registration)
    if status_filter and status_filter != "all":
        query = query.filter(Registration.status == status_filter)
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

    registrations = query.order_by(Registration.created_at.desc()).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0B1E3B')
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#4B5563')
    )

    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    filter_label = f"Filtro: {status_filter}" if status_filter and status_filter != "all" else "Todas as Inscrições"
    elements.append(Paragraph("MIIC 2026 — Mozambique International Investment Congress", title_style))
    elements.append(Paragraph(f"Relatório Oficial de Inscrições | {filter_label} | Emitido em: {now_str} | Total: {len(registrations)} participantes", subtitle_style))
    elements.append(Spacer(1, 12))

    headers = ["#", "Nome Completo", "Email", "Telefone", "Organização", "País", "Perfil", "Status", "Data"]
    table_data = [headers]

    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )

    for reg in registrations:
        profile_label = PROFILE_LABELS.get(reg.participant_type, reg.participant_type or "Outro")
        status_label = STATUS_LABELS.get(reg.status, reg.status)
        created_str = reg.created_at.strftime("%d/%m/%Y") if reg.created_at else ""
        table_data.append([
            str(reg.id),
            Paragraph(reg.full_name[:35], cell_style),
            Paragraph(reg.email[:35], cell_style),
            reg.phone or "-",
            Paragraph((reg.organization or "-")[:28], cell_style),
            reg.country[:22],
            profile_label,
            status_label,
            created_str,
        ])

    col_widths = [25, 120, 140, 85, 120, 85, 95, 70, 60]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B1E3B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
    ]))
    elements.append(t)
    doc.build(elements)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=inscricoes_miic_2026.pdf"}
    )
