import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from app.config import Settings

class SmtpSettingsTests(unittest.TestCase):
    def test_gmail_legacy_user_and_sender_fallback(self):
        with patch.dict('os.environ', {'SMTP_HOST':'smtp.gmail.com', 'SMTP_PORT':'587', 'SMTP_USERNAME':'', 'SMTP_USER':'sender@example.com', 'SMTP_PASSWORD':'abcd efgh ijkl mnop'}, clear=True):
            cfg = Settings(_env_file=None, jwt_secret='x'*40, data_key=Fernet.generate_key().decode())
        self.assertEqual(cfg.smtp_username, 'sender@example.com')
        self.assertEqual(cfg.smtp_from, 'sender@example.com')
        self.assertEqual(cfg.smtp_password.get_secret_value(), 'abcdefghijklmnop')
        self.assertEqual(cfg.smtp_port, 587)
