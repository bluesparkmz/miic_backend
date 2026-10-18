from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel, EmailStr, Field, ConfigDict, AliasChoices

# ==========================================
# Registration Schemas (English fields)
# ==========================================

class RegistrationBase(BaseModel):
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description="Full name of attendee",
        validation_alias=AliasChoices("full_name", "nome", "name")
    )
    email: EmailStr = Field(
        ...,
        description="Valid email address for registration confirmation"
    )
    phone: Optional[str] = Field(
        None,
        max_length=50,
        description="Phone or WhatsApp contact",
        validation_alias=AliasChoices("phone", "telefone")
    )
    organization: Optional[str] = Field(
        None,
        max_length=150,
        description="Company or organization",
        validation_alias=AliasChoices("organization", "organizacao", "company")
    )
    country: str = Field(
        ...,
        min_length=2,
        max_length=80,
        description="Country of origin / residence",
        validation_alias=AliasChoices("country", "pais")
    )
    participant_type: Optional[str] = Field(
        "0",
        max_length=60,
        description="Participant profile (e.g. 0=Investor, 1=Company, 2=Government, etc.)",
        validation_alias=AliasChoices("participant_type", "tipo", "type")
    )
    message: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional message or investment focus",
        validation_alias=AliasChoices("message", "mensagem")
    )


class RegistrationCreate(RegistrationBase):
    pass


class RegistrationStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        pattern="^(pending|confirmed|cancelled|pendente|confirmado|cancelado)$",
        description="New registration status"
    )


class RegistrationResponse(RegistrationBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ==========================================
# User / Admin Schemas (English fields)
# ==========================================

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100, description="Admin password")


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: int
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None


# ==========================================
# Dashboard & Analytics Schemas (English)
# ==========================================

class DashboardStats(BaseModel):
    total_registrations: int
    pending: int
    confirmed: int
    cancelled: int
    by_country: Dict[str, int]
    by_type: Dict[str, int]
