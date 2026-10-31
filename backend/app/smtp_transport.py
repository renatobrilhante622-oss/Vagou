"""TLS-authenticated SMTP transport, independent of database and worker imports."""
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings


def email_configured() -> bool:
    cfg = settings()
    credentials_present = bool(cfg.smtp_username and cfg.smtp_password and cfg.smtp_password.get_secret_value())
    if cfg.smtp_host.casefold() == 'smtp.gmail.com':
        return bool(cfg.smtp_from and credentials_present)
    return bool(cfg.smtp_host and cfg.smtp_from and (not cfg.smtp_username or credentials_present))


def deliver_confirmation(recipient: str, code: str):
    if not email_configured():
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
    context = ssl.create_default_context()
    if cfg.smtp_security == 'ssl':
        connection = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds, context=context)
    else:
        connection = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds)
    try:
        with connection as smtp:
            if cfg.smtp_security == 'starttls':
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            if cfg.smtp_username:
                smtp.login(cfg.smtp_username, cfg.smtp_password.get_secret_value())
            smtp.send_message(message)
    finally:
        connection.close()
