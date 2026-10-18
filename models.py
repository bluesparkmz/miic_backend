from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from database import Base

class User(Base):
    """
    Administrator User Model.
    Used exclusively for admin authentication and management.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<User id={self.id} username='{self.username}' is_admin={self.is_admin}>"


class Registration(Base):
    """
    Event Registration Model.
    All fields are in English, mapping directly to conference attendees:
    - full_name: Attendee's full name
    - email: Contact email address
    - phone: Phone / WhatsApp number
    - organization: Company, institution or organization
    - country: Country of origin or residence
    - participant_type: Attendee profile (Investor, Company, Government, Media, Other)
    - message: Optional message or investment interest description
    - status: Registration status ('pending', 'confirmed', 'cancelled')
    """
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(120), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    organization = Column(String(150), nullable=True)
    country = Column(String(80), nullable=False, index=True)
    participant_type = Column(String(60), nullable=False, default="0", index=True)
    message = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Registration id={self.id} full_name='{self.full_name}' email='{self.email}' country='{self.country}' status='{self.status}'>"
