"""Verified TLS SMTP transport with diagnostics that never expose mail contents."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def configure_smtp_logging() -> None:
    """Uvicorn does not configure the application's INFO handlers by default."""
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(levelname)s %(name)s %(message)s'))
        logger.addHandler(handler)
    logger.propagate = False


def email_configured() -> bool:
    cfg = settings()
    credentials_present = bool(cfg.smtp_username and cfg.smtp_password and cfg.smtp_password.get_secret_value())
    if cfg.smtp_host.casefold() == 'smtp.gmail.com':
        return bool(cfg.smtp_from and credentials_present)
    return bool(cfg.smtp_host and cfg.smtp_from and (not cfg.smtp_username or credentials_present))


def _failure_category(error: Exception) -> str:
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return 'authentication'
    if isinstance(error, ssl.SSLError):
        return 'tls'
    if isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected)):
        return 'connection'
    if isinstance(error, smtplib.SMTPException):
        return 'provider'
    if isinstance(error, OSError):
        return 'connection'
    return 'transport'


def deliver_confirmation(recipient: str, code: str):
    if not email_configured():
        logger.error('SMTP delivery_unavailable category=configuration')
        raise RuntimeError('Email transport is not configured')
    cfg = settings()
    message = EmailMessage()
    message['From'] = cfg.smtp_from
    message['To'] = recipient
    message['Subject'] = 'Confirme seu e-mail no Vagou!'
    message.set_content(
        f'Bem-vindo ao Vagou!\n\nSeu código de confirmação é: {code}\n\n'
        f'Ele expira em {cfg.verification_expiry_minutes} minutos. '
        'Não compartilhe este código. Se você não solicitou o cadastro, ignore esta mensagem.\n'
    )
    connection = None
    phase = 'connecting'
    try:
        logger.info('SMTP delivery_started phase=%s security=%s port=%s', phase, cfg.smtp_security, cfg.smtp_port)
        context = ssl.create_default_context()
        if cfg.smtp_security == 'ssl':
            connection = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds, context=context)
        else:
            connection = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds)
        if cfg.smtp_security == 'starttls':
            phase = 'starttls'
            logger.info('SMTP delivery_progress phase=%s', phase)
            connection.ehlo()
            connection.starttls(context=context)
            connection.ehlo()
        if cfg.smtp_username:
            phase = 'authenticating'
            logger.info('SMTP delivery_progress phase=%s', phase)
            connection.login(cfg.smtp_username, cfg.smtp_password.get_secret_value())
        phase = 'sending'
        logger.info('SMTP delivery_progress phase=%s', phase)
        connection.send_message(message)
        # Accepted by SMTP is not a guarantee of arrival in the inbox.
        logger.info('SMTP delivery_accepted phase=%s', phase)
    except Exception as error:
        status = getattr(error, 'smtp_code', None)
        logger.error('SMTP delivery_failed phase=%s category=%s error_type=%s smtp_code=%s',
                     phase, _failure_category(error), type(error).__name__,
                     status if isinstance(status, int) else 'unavailable')
        # Provider messages may contain addresses, credentials or message bytes:
        # never log str(error), exc_info, the envelope, or SMTP wire debugging.
        raise
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception as error:
                # Cleanup must not mask the original exception or turn an
                # accepted message into a failed delivery/retry.
                logger.error('SMTP cleanup_failed error_type=%s', type(error).__name__)
