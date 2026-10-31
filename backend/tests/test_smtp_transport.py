"""SMTP transport contract with real verified TLS contexts and mocked sockets."""
import io
import smtplib
import ssl
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from app.smtp_transport import deliver_confirmation, email_configured


def transport_settings(**overrides):
    fields = dict(smtp_host='smtp.gmail.com', smtp_port=587, smtp_username='sender@example.com',
                  smtp_password=SimpleNamespace(get_secret_value=lambda: 'test-app-password'),
                  smtp_from='Vagou! <sender@example.com>', smtp_security='starttls',
                  smtp_timeout_seconds=13, verification_expiry_minutes=10)
    fields.update(overrides)
    return SimpleNamespace(**fields)


class SmtpTransportContract(unittest.TestCase):
    def connection(self):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        return connection

    def test_starttls_verifies_certificate_before_authentication_and_send(self):
        connection = self.connection()
        output = io.StringIO()
        with patch('app.smtp_transport.settings', return_value=transport_settings()), \
             patch('app.smtp_transport.smtplib.SMTP', return_value=connection) as factory, \
             patch('app.smtp_transport.smtplib.SMTP_SSL') as ssl_factory, \
             redirect_stdout(output), redirect_stderr(output):
            deliver_confirmation('candidate@example.com', '001234')
        factory.assert_called_once_with('smtp.gmail.com', 587, timeout=13)
        ssl_factory.assert_not_called()
        context = connection.starttls.call_args.kwargs['context']
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        calls = connection.mock_calls
        self.assertLess(calls.index(call.starttls(context=context)), calls.index(call.login('sender@example.com', 'test-app-password')))
        message = connection.send_message.call_args.args[0]
        self.assertLess(calls.index(call.login('sender@example.com', 'test-app-password')), calls.index(call.send_message(message)))
        self.assertEqual(message['To'], 'candidate@example.com')
        self.assertIn('001234', message.get_content())
        self.assertNotIn('test-app-password', message.as_string())
        self.assertNotIn('001234', output.getvalue())
        self.assertNotIn('test-app-password', output.getvalue())
        connection.close.assert_called_once()

    def test_ssl_mode_provides_verified_tls_context_at_connection(self):
        connection = self.connection()
        with patch('app.smtp_transport.settings', return_value=transport_settings(smtp_security='ssl', smtp_port=465)), \
             patch('app.smtp_transport.smtplib.SMTP_SSL', return_value=connection) as factory, \
             patch('app.smtp_transport.smtplib.SMTP') as plain_factory:
            deliver_confirmation('candidate@example.com', '001234')
        plain_factory.assert_not_called()
        arguments = factory.call_args
        self.assertEqual(arguments.args, ('smtp.gmail.com', 465))
        self.assertEqual(arguments.kwargs['timeout'], 13)
        self.assertTrue(arguments.kwargs['context'].check_hostname)
        self.assertEqual(arguments.kwargs['context'].verify_mode, ssl.CERT_REQUIRED)
        connection.starttls.assert_not_called()
        connection.login.assert_called_once_with('sender@example.com', 'test-app-password')
        connection.send_message.assert_called_once()

    def test_gmail_requires_sender_and_nonempty_credentials(self):
        for overrides in [{'smtp_username': ''}, {'smtp_password': None},
                          {'smtp_password': SimpleNamespace(get_secret_value=lambda: '')},
                          {'smtp_from': ''}]:
            with self.subTest(fields=tuple(overrides)):
                with patch('app.smtp_transport.settings', return_value=transport_settings(**overrides)), \
                     patch('app.smtp_transport.smtplib.SMTP') as factory:
                    self.assertFalse(email_configured())
                    with self.assertRaises(RuntimeError):
                        deliver_confirmation('candidate@example.com', '001234')
                    factory.assert_not_called()

    def test_unconfigured_transport_stays_unavailable(self):
        with patch('app.smtp_transport.settings', return_value=transport_settings(smtp_host='')):
            self.assertFalse(email_configured())

    def test_delivery_failure_propagates_for_outbox_retry(self):
        connection = self.connection()
        connection.send_message.side_effect = smtplib.SMTPException('Delivery rejected')
        with patch('app.smtp_transport.settings', return_value=transport_settings()), \
             patch('app.smtp_transport.smtplib.SMTP', return_value=connection):
            with self.assertRaises(smtplib.SMTPException):
                deliver_confirmation('candidate@example.com', '001234')
        connection.close.assert_called_once()

    def test_tls_failure_prevents_authentication_and_delivery(self):
        connection = self.connection()
        connection.starttls.side_effect = ssl.SSLError('Handshake failed')
        with patch('app.smtp_transport.settings', return_value=transport_settings()), \
             patch('app.smtp_transport.smtplib.SMTP', return_value=connection):
            with self.assertRaises(ssl.SSLError):
                deliver_confirmation('candidate@example.com', '001234')
        connection.login.assert_not_called()
        connection.send_message.assert_not_called()
        connection.close.assert_called_once()
