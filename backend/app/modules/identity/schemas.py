from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None


class UserCreate(UserBase):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt reads at most 72 bytes; a longer password used to fail with a server error.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes long (about 72 letters or digits).")
        return value


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=1024)


class UserRead(UserBase):
    id: UUID
    is_active: bool
    is_superuser: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserRead


class QuickRegister(BaseModel):
    """'Register now' on the public site: name, email, phone, company, designation and a password."""

    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone_number: str = Field(..., min_length=6, max_length=32)
    company: str = Field(..., min_length=1, max_length=255)
    designation: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=8, description="At least 8 characters")

    @field_validator("password")
    @classmethod
    def _password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes long (about 72 letters or digits).")
        return value

    @field_validator("phone_number")
    @classmethod
    def _phone_has_digits(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 6:
            raise ValueError("Enter a phone number with at least 6 digits.")
        return value


class SignupRead(BaseModel):
    """One 'Register now' sign-up, for the admin console."""

    id: UUID
    full_name: str
    email: str
    phone_number: Optional[str] = None
    company: Optional[str] = None
    designation: Optional[str] = None
    registered_at: Optional[datetime] = None
    is_active: bool
