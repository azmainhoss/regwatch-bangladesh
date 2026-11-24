from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
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

from backend.app.modules.identity.schemas import QuickRegister, SignupRead, TokenResponse, UserCreate, UserLogin, UserRead

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


def _digits(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


@router.post("/quick-register", response_model=TokenResponse)
async def quick_register(
    payload: QuickRegister,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    'Register now' on the public site: no password. A new email gets an account at once.
    The same email again (another device) gets back in only with the same phone number,
    so typing someone else's email is not enough. Password accounts (admins, banks) must sign in.
    """
    ratelimit.enforce(f"register:{ratelimit.client_ip(request)}", *REGISTER_PER_IP,
                      detail="Too many registrations from this network. Please try again later.")
    email = payload.email.lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            # Unusable password: nobody knows it, so password sign-in never works for this account.
            hashed_password=get_password_hash(secrets.token_urlsafe(48)[:64]),
            full_name=payload.full_name,
            phone_number=payload.phone_number,
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        await db.flush()
        db.add(UserProfile(
            user_id=user.id,
            designation=payload.designation,
            preferences={"signup": QUICK_SIGNUP, "company": payload.company},
        ))
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="This email was just registered. Please try again.")
    else:
        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
        prefs = dict(profile.preferences or {}) if profile is not None else {}
        if prefs.get("signup") != QUICK_SIGNUP or user.is_superuser:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="This email already has a password account. Please sign in instead.")
        fails_key = f"quick-fail:{email}"
        if ratelimit.limiter.count(fails_key, LOGIN_FAILS_PER_EMAIL[1]) >= LOGIN_FAILS_PER_EMAIL[0]:
            raise ratelimit.too_many("Too many attempts for this email. Please wait 15 minutes and try again.",
                                     LOGIN_FAILS_PER_EMAIL[1])
        if not secrets.compare_digest(_digits(user.phone_number), _digits(payload.phone_number)):
            ratelimit.limiter.add(fails_key)
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="This email is already registered. Use the phone number you registered with.")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")
        user.full_name = payload.full_name
        prefs["company"] = payload.company
        if profile is not None:
            profile.designation = payload.designation
            profile.preferences = prefs
        await db.commit()
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

    token = _token_for(user)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserRead.model_validate(user)
    )


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


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
