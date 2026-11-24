"""One-click unsubscribe from the daily digest (no sign-in needed; the signed token is the proof).

POST /email/unsubscribe/{token}: mail apps call this for "Unsubscribe" (RFC 8058, List-Unsubscribe-Post), and the
/u/<token> page calls it after the person clicks the link in an email footer.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database.session import get_async_db
from backend.app.modules.alerts import reader_mail
from backend.app.modules.identity.models import User

router = APIRouter(prefix="/email", tags=["Email"])


@router.post("/unsubscribe/{token}")
async def unsubscribe(token: str, db: AsyncSession = Depends(get_async_db)):
    uid = reader_mail.read_unsubscribe_token(token)
    if uid is None or await db.get(User, uid) is None:
        raise HTTPException(status_code=400, detail="This unsubscribe link is not valid.")
    await reader_mail.unsubscribe(db, uid)
    return {"ok": True, "message": "You will no longer get the daily digest. You can turn it back on in Email settings."}
