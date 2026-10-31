"""Identity/schema checks run when the backend's actual dependencies are installed."""
import importlib.util
import unittest

READY = bool(importlib.util.find_spec('email_validator'))


@unittest.skipUnless(READY, 'email-validator dependency unavailable; identity schema checks not executed')
class IdentitySchemas(unittest.TestCase):
    def test_cnpj_check_digits_and_formats(self):
        from app.schemas import Register, valid_cnpj
        self.assertTrue(valid_cnpj('11222333000181'))
        self.assertFalse(valid_cnpj('11222333000182'))
        self.assertFalse(valid_cnpj('00000000000000'))
        self.assertTrue(valid_cnpj('12ABC34501DE35'))
        self.assertFalse(valid_cnpj('12ABCD00000100'))
        data = {'email': 'empresa@example.com', 'password': 'Corporate-Password-2026!', 'name': 'Contato', 'role': 'recruiter', 'privacy_version': '2026-01', 'consent': True,
                'company_cnpj': '11.222.333/0001-81', 'company_name': 'Empresa Ltda', 'company_contact_email': 'contato@gmail.com', 'company_phone': '+5511999999999'}
        self.assertEqual(Register(**data).company_cnpj, '11222333000181')
        self.assertEqual(Register(**{**data, 'password': '  Password with spaces  '}).password, '  Password with spaces  ')
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            Register(**{**data, 'company_name': None})
        with self.assertRaises(ValidationError):
            Register(**{**data, 'role': 'candidate'})

    def test_location_required_for_onsite_and_hybrid(self):
        from app.schemas import Preferences
        from pydantic import ValidationError
        for modality in ['onsite', 'hybrid']:
            with self.assertRaises(ValidationError):
                Preferences(modalities=[modality])
            self.assertEqual(Preferences(modalities=[modality], locations=['Recife, PE']).locations, ['Recife, PE'])
        self.assertEqual(Preferences(modalities=['remote']).locations, [])

    def test_code_preserves_leading_zero_and_rejects_wrong_shape(self):
        from app.schemas import VerifyEmail
        from pydantic import ValidationError
        self.assertEqual(VerifyEmail(email='ana@example.com', code='001234').code, '001234')
        for code in ['12345', '1234567', 'ABCDEF', 123456]:
            with self.assertRaises(ValidationError):
                VerifyEmail(email='ana@example.com', code=code)

    def test_automation_interval_bounds(self):
        from app.schemas import Preferences
        from pydantic import ValidationError
        self.assertEqual(Preferences().automation_interval_minutes, 60)
        self.assertEqual(Preferences(automation_interval_minutes=15).automation_interval_minutes, 15)
        self.assertEqual(Preferences(automation_interval_minutes=1440).automation_interval_minutes, 1440)
        for interval in [0, 14, 1441]:
            with self.assertRaises(ValidationError):
                Preferences(automation_interval_minutes=interval)

    def test_public_job_contract_omits_private_moderation_fields(self):
        from app.schemas import JobOut, PublicJobOut
        self.assertNotIn('moderation_note', PublicJobOut.model_fields)
        self.assertNotIn('moderated_at', PublicJobOut.model_fields)
        self.assertIn('moderation_note', JobOut.model_fields)
        self.assertIn('moderated_at', JobOut.model_fields)
