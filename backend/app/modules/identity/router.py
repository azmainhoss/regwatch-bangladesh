from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core import ratelimit
from backend.app.core.security import (
    burn_password_check,
    create_access_token,
    get_password_hash,
    password_fingerprint,
    verify_password,
)
from backend.app.database.session import get_async_db
from backend.app.modules.identity.deps import get_current_superuser, get_current_user
from backend.app.modules.identity.models import User, UserProfile
import secrets

from backend.app.modules.identity.schemas import ProfileUpdate, QuickRegister, SignupRead, TokenResponse, UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["Identity & Auth"])

# Brute-force limits (one server, one process). A person typing never gets near them.
LOGIN_PER_IP = (30, 300)  # failed sign-ins from one address per 5 minutes
LOGIN_FAILS_PER_EMAIL = (20, 900)  # wrong passwords for one account per 15 minutes, from anywhere
REGISTER_PER_IP = (30, 3600)  # new accounts from one address per hour (a bank may sign up a team at once)


# Visitors who registered with 'Register now' stay in for 30 days; password accounts keep the normal expiry.
QUICK_TOKEN_MINUTES = 30 * 24 * 60


def _token_for(user: User, minutes: int | None = None) -> str:
    return create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims={"pwv": password_fingerprint(user.hashed_password)},
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    ratelimit.enforce(f"register:{ratelimit.client_ip(request)}", *REGISTER_PER_IP,
                      detail="Too many new accounts from this network. Please try again later.")
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    user = User(
        email=payload.email.lower(),
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        is_active=True,
        is_superuser=False
    )
    db.add(user)
    await db.flush()

    profile = UserProfile(user_id=user.id, preferences={})
    db.add(profile)
    try:
        await db.commit()
    except IntegrityError:
        # Two sign-ups with the same email at the same moment.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    await db.refresh(user)

    token = _token_for(user)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user)
    )


QUICK_SIGNUP = "quick"


@router.post("/quick-register", response_model=TokenResponse)
async def quick_register(
    payload: QuickRegister,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    'Register now' on the public site: name, email, phone, company, designation and a password.
    Signed in at once (30-day session). Next time the person signs in with that email and password.
    """
    ratelimit.enforce(f"register:{ratelimit.client_ip(request)}", *REGISTER_PER_IP,
                      detail="Too many registrations from this network. Please try again later.")
    email = payload.email.lower()
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This email is already registered. Please sign in with your password.")
    user = User(
        email=email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name or "",
        phone_number=payload.phone_number,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()
    db.add(UserProfile(
        user_id=user.id,
        designation=payload.designation,
        preferences={"signup": QUICK_SIGNUP, **({"company": payload.company} if payload.company else {})},
    ))
    # No welcome email (owner, 2026-11-25).
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This email is already registered. Please sign in with your password.")
    await db.refresh(user)

    return TokenResponse(
        access_token=_token_for(user, QUICK_TOKEN_MINUTES),
        token_type="bearer",
        expires_in_seconds=QUICK_TOKEN_MINUTES * 60,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    req_email = payload.email.lower()
    # Only failed sign-ins count, so many colleagues behind one office address can all sign in.
    ip_key = f"login-ip:{ratelimit.client_ip(request)}"
    if ratelimit.limiter.count(ip_key, LOGIN_PER_IP[1]) >= LOGIN_PER_IP[0]:
        raise ratelimit.too_many("Too many sign-in attempts. Please wait a few minutes and try again.", LOGIN_PER_IP[1])
    fails_key = f"login-fail:{req_email}"
    if ratelimit.limiter.count(fails_key, LOGIN_FAILS_PER_EMAIL[1]) >= LOGIN_FAILS_PER_EMAIL[0]:
        raise ratelimit.too_many("Too many wrong passwords for this account. Please wait 15 minutes and try again.",
                                 LOGIN_FAILS_PER_EMAIL[1])
    res = await db.execute(select(User).where(User.email == req_email))
    user = res.scalar_one_or_none()
    if user is None:
        burn_password_check(payload.password)
    if not user or not verify_password(payload.password, user.hashed_password):
        ratelimit.limiter.add(fails_key)
        ratelimit.limiter.add(ip_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    # Readers stay signed in for 30 days; administrators keep the shorter default session.
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES if user.is_superuser else QUICK_TOKEN_MINUTES
    token = _token_for(user, minutes)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=minutes * 60,
        user=UserRead.model_validate(user)
    )


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


RESET_PER_IP = (10, 3600)  # reset requests from one address per hour
RESET_PER_EMAIL = (3, 3600)  # reset emails to one address per hour


class ResetRequest(BaseModel):
    email: EmailStr


class ResetConfirm(BaseModel):
    token: str = Field(..., min_length=10, max_length=400)
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes long (about 72 letters or digits).")
        return value


@router.post("/password-reset/request")
async def request_password_reset(payload: ResetRequest, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Emails a one-hour reset link if the address has an account. Always answers the same way, so it cannot be
    used to find out who is registered."""
    from backend.app.modules.alerts import reader_mail

    ratelimit.enforce(f"reset-ip:{ratelimit.client_ip(request)}", *RESET_PER_IP,
                      detail="Too many reset requests from this network. Please try again later.")
    from backend.app.modules.alerts import mailer

    if not mailer.email_configured():
        # Email is switched off (owner, 2026-11-25): say so instead of promising a link that never comes.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Password reset by email is not available yet. Please write to insights@amarcircular.com and we will help you.")
    email = payload.email.lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None and user.is_active and ratelimit.limiter.count(f"reset-email:{email}", RESET_PER_EMAIL[1]) < RESET_PER_EMAIL[0]:
        ratelimit.limiter.add(f"reset-email:{email}")
        reader_mail.queue_reset(db, user)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
    return {"ok": True, "message": "If that email is registered, a reset link is on its way. It works for one hour."}


@router.post("/password-reset/confirm", response_model=TokenResponse)
async def confirm_password_reset(payload: ResetConfirm, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Sets a new password from a valid reset link, then signs the person in."""
    from backend.app.modules.alerts import reader_mail

    ratelimit.enforce(f"reset-confirm:{ratelimit.client_ip(request)}", *RESET_PER_IP,
                      detail="Too many attempts. Please try again later.")
    parsed = reader_mail.parse_reset_token(payload.token)
    user = await db.get(User, parsed[0]) if parsed else None
    if user is None or not user.is_active or not reader_mail.reset_token_valid(payload.token, user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This reset link has expired or was already used. Please ask for a new one.")
    user.hashed_password = get_password_hash(payload.password)
    await db.commit()
    await db.refresh(user)
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES if user.is_superuser else QUICK_TOKEN_MINUTES
    return TokenResponse(access_token=_token_for(user, minutes), token_type="bearer",
                         expires_in_seconds=minutes * 60, user=UserRead.model_validate(user))


@router.patch("/me/profile", response_model=UserRead)
async def update_my_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Sign-up steps 2 (name, phone) and 3 (company, designation). Only the fields sent change."""
    user = await db.get(User, current_user.id)
    sent = payload.model_dump(exclude_unset=True)
    if "full_name" in sent and sent["full_name"]:
        user.full_name = sent["full_name"]
    if "phone_number" in sent:
        user.phone_number = sent["phone_number"]
    if "company" in sent or "designation" in sent:
        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
        if profile is None:
            profile = UserProfile(user_id=user.id, preferences={})
            db.add(profile)
        if sent.get("designation"):
            profile.designation = sent["designation"]
        if sent.get("company"):
            profile.preferences = {**(profile.preferences or {}), "company": sent["company"]}
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/admin/signups", response_model=list[SignupRead])
async def list_signups(
    _admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_async_db),
):
    """Everyone who used 'Register now', newest first (administrators only)."""
    rows = (
        await db.execute(
            select(User, UserProfile).join(UserProfile, UserProfile.user_id == User.id).order_by(User.created_at.desc())
        )
    ).all()
    out: list[SignupRead] = []
    for user, profile in rows:
        prefs = profile.preferences or {}
        if prefs.get("signup") != QUICK_SIGNUP:
            continue
        out.append(SignupRead(
            id=user.id, full_name=user.full_name, email=user.email, phone_number=user.phone_number,
            company=prefs.get("company"), designation=profile.designation,
            registered_at=user.created_at, is_active=user.is_active,
        ))
    return out
