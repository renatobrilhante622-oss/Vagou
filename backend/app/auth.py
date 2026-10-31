"""Account creation and single-use, bounded-attempt email confirmation."""
import asyncio
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import session
from app.mailer import email_configured, process_email_outbox
from app.models import EmailOutbox, EmailVerification, User
from app.schemas import Login, Register, ResendVerification, VerifyEmail
from app.security import DUMMY_HASH, cipher, current_user, hash_password, token, verify_password
from app.verification_debug import log_verification_fallback

router = APIRouter(prefix='/v1/auth', tags=['Autenticação'])
logger = logging.getLogger('uvicorn.error')


def verification_digest(user_id: uuid.UUID, version: uuid.UUID, code: str) -> str:
    # Keyed digest prevents offline brute force over the one-million-code space.
    message = f'email-verification:{user_id}:{version}:{code}'.encode()
    return hmac.new(settings().jwt_secret.get_secret_value().encode(), message, hashlib.sha256).hexdigest()


async def queue_verification(db: AsyncSession, user: User, challenge: EmailVerification | None = None):
    now = datetime.now(timezone.utc)
    code = f'{secrets.randbelow(1_000_000):06d}'
    version = uuid.uuid4()
    if challenge is None:
        challenge = EmailVerification(user_id=user.id)
        db.add(challenge)
    challenge.version = version
    challenge.code_digest = verification_digest(user.id, version, code)
    challenge.expires_at = now + timedelta(minutes=settings().verification_expiry_minutes)
    challenge.sent_at = now
    challenge.attempts = 0
    # Older codes and delivery payloads are invalidated on resend.
    await db.execute(delete(EmailOutbox).where(EmailOutbox.user_id == user.id))
    db.add(EmailOutbox(user_id=user.id, verification_version=version,
                       code_encrypted=cipher().encrypt(code.encode()).decode(),
                       next_attempt_at=now))
    return code


async def attempt_verification_delivery(user_id: uuid.UUID, code: str) -> str:
    """Invoked after account/code commit. Delivery never rolls back registration."""
    status = 'configuration_required'
    if email_configured():
        try:
            result = await asyncio.wait_for(
                process_email_outbox(batch_size=1, only_user_id=user_id),
                timeout=settings().verification_delivery_timeout_seconds,
            )
            status = 'sent' if result['sent'] else 'retrying'
        except Exception as error:
            logger.error('verification_dispatch_failed error_type=%s', type(error).__name__)
            status = 'retrying'
    else:
        logger.error('verification_smtp_configuration_incomplete')
    if status != 'sent':
        log_verification_fallback(code)
    return status


def account_response(user: User) -> dict:
    return {'id': user.id, 'email': user.email, 'name': user.name, 'role': user.role,
            'skills': user.skills, 'is_premium': user.is_premium,
            'automation_enabled': user.automation_enabled, 'has_resume': bool(user.resume_key),
            'preferences': user.preferences, 'email_verified': user.email_verified,
            'verification_required': not user.email_verified,
            'company_cnpj': user.company_cnpj, 'company_name': user.company_name,
            'company_contact_email': user.company_contact_email}


@router.post('/register', status_code=201)
async def register(payload: Register, db: AsyncSession = Depends(session)):
    if payload.privacy_version != settings().privacy_version:
        raise HTTPException(422, 'Aceite a versão atual da política de privacidade.')
    user = User(email=str(payload.email).casefold(), name=payload.name, role=payload.role,
                password_hash=await asyncio.to_thread(hash_password, payload.password),
                privacy_version=payload.privacy_version, email_verified=False,
                company_cnpj=payload.company_cnpj, company_name=payload.company_name,
                company_contact_email=str(payload.company_contact_email).casefold() if payload.company_contact_email else None,
                phone_encrypted=cipher().encrypt(payload.company_phone.encode()).decode() if payload.company_phone else None)
    db.add(user)
    try:
        await db.flush()
        code = await queue_verification(db, user)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Já existe cadastro com este e-mail ou CNPJ. Entre na sua conta ou solicite um novo código.') from None
    delivery_status = await attempt_verification_delivery(user.id, code)
    message = {
        'sent': 'Código de confirmação enviado. Verifique também a pasta de spam.',
        'retrying': 'O e-mail ainda não foi entregue. O serviço continuará tentando; você também pode solicitar outro código.',
        'configuration_required': 'Cadastro salvo, mas o envio de e-mail precisa ser configurado pelo operador.'
    }[delivery_status]
    return {**account_response(user), 'delivery_status': delivery_status, 'message': message}



@router.post('/login')
async def login(payload: Login, db: AsyncSession = Depends(session)):
    user = await db.scalar(select(User).where(User.email == str(payload.email).casefold()))
    valid = await asyncio.to_thread(verify_password, payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        raise HTTPException(401, 'E-mail ou senha incorretos. Confira seus dados e tente novamente.')
    if not user.email_verified:
        raise HTTPException(403, {'code': 'email_verification_required', 'message': 'Confirme seu e-mail com o código recebido para entrar.'})
    return {'access_token': token(user), 'token_type': 'bearer', 'expires_in': settings().access_minutes * 60}


@router.post('/verify-email')
async def verify_email(payload: VerifyEmail, db: AsyncSession = Depends(session)):
    # Uniform failure avoids confirming whether an address exists.
    invalid = HTTPException(400, 'Código inválido ou expirado. Confira os seis dígitos ou solicite um novo código.')
    user = await db.scalar(select(User).where(User.email == str(payload.email).casefold()).with_for_update())
    if not user or user.email_verified:
        raise invalid
    challenge = await db.get(EmailVerification, user.id, with_for_update=True)
    now = datetime.now(timezone.utc)
    if not challenge or challenge.expires_at <= now or challenge.attempts >= settings().verification_max_attempts:
        raise invalid
    challenge.attempts += 1
    expected = verification_digest(user.id, challenge.version, payload.code)
    if not hmac.compare_digest(challenge.code_digest, expected):
        await db.commit()  # Failed attempts must survive the error response.
        raise invalid
    user.email_verified = True
    await db.delete(challenge)
    await db.execute(delete(EmailOutbox).where(EmailOutbox.user_id == user.id))
    await db.commit()
    return {'verified': True, 'message': 'E-mail confirmado. Você já pode entrar no Vagou!'}


@router.post('/resend-verification', status_code=202)
async def resend(payload: ResendVerification, db: AsyncSession = Depends(session)):
    # Same reply for missing, verified and rate-limited accounts.
    response = {'message': 'Se este e-mail estiver aguardando confirmação, um novo código será agendado. Aguarde um minuto antes de solicitar novamente.',
                'delivery_status': 'pending' if email_configured() else 'configuration_required'}
    user = await db.scalar(select(User).where(User.email == str(payload.email).casefold()).with_for_update())
    if not user or user.email_verified:
        return response
    challenge = await db.get(EmailVerification, user.id, with_for_update=True)
    if challenge and (datetime.now(timezone.utc) - challenge.sent_at).total_seconds() < settings().verification_resend_seconds:
        return response
    code = await queue_verification(db, user, challenge)
    await db.commit()
    await attempt_verification_delivery(user.id, code)
    return response


@router.post('/logout', status_code=204)
async def logout(user: User = Depends(current_user), db: AsyncSession = Depends(session)):
    locked = await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked:
        locked.token_version += 1
        await db.commit()
    return Response(status_code=204)
