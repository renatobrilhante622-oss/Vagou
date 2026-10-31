import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.passwords import hash_password, verify_password
from app.config import settings
from app.db import session
from app.models import User

bearer = HTTPBearer(auto_error=False)


DUMMY_HASH = hash_password(secrets.token_hex(32))


def token(user: User) -> str:
    cfg = settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': str(user.id), 'ver': user.token_version, 'iat': now, 'exp': now + timedelta(minutes=cfg.access_minutes), 'iss': cfg.issuer, 'aud': cfg.audience, 'jti': secrets.token_hex(16)}, cfg.jwt_secret.get_secret_value(), algorithm='HS256')


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: AsyncSession = Depends(session)) -> User:
    from uuid import UUID
    try:
        if credentials is None:
            raise ValueError
        cfg = settings()
        claims = jwt.decode(credentials.credentials, cfg.jwt_secret.get_secret_value(), algorithms=['HS256'], issuer=cfg.issuer, audience=cfg.audience, options={'require': ['sub', 'exp', 'iat', 'ver', 'jti']})
        user = await db.get(User, UUID(claims['sub']))
        if not user or user.token_version != claims['ver']:
            raise ValueError
        return user
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Invalid or expired token', headers={'WWW-Authenticate': 'Bearer'}) from None


def role(required: str):
    async def dependency(user: User = Depends(current_user)):
        if user.role != required:
            raise HTTPException(403, 'Role not allowed')
        return user
    return dependency


def cipher() -> Fernet:
    return Fernet(settings().data_key.get_secret_value().encode())
