"""Local regression coverage for professional catalog and input normalization."""
import importlib.util
import unittest

READY = bool(importlib.util.find_spec('email_validator') and importlib.util.find_spec('sqlalchemy'))


@unittest.skipUnless(READY, 'Backend dependencies unavailable')
class ProductContracts(unittest.TestCase):
    def test_each_course_has_distinct_syllabus_and_explicit_workload(self):
        from app.courses import COURSES
        self.assertEqual(len(COURSES), len({course['id'] for course in COURSES}))
        self.assertEqual(len(COURSES), len({tuple(course['syllabus']) for course in COURSES}))
        for course in COURSES:
            self.assertGreaterEqual(len(course['syllabus']), 3)
            self.assertTrue(course['workload'])
            self.assertTrue(course['url'].startswith('https://'))

    def test_brazilian_phones_and_cnpj_formats(self):
        from app.schemas import ProfileUpdate, Register
        profile = ProfileUpdate(name='Maria Teste', skills=['Python'], phone='(61) 99999-9999')
        self.assertEqual(profile.phone, '+5561999999999')
        corporate = Register(email='contato@example.org', password='Senha-Forte-Teste-123',
            name='Empresa de Teste', role='recruiter', privacy_version='2026-01', consent=True,
            company_cnpj='11.222.333 / 0001-81', company_name='Empresa',
            company_contact_email='contato@example.org', company_phone='(61) 3333-4444')
        self.assertEqual(corporate.company_cnpj, '11222333000181')
        self.assertEqual(corporate.company_phone, '+556133334444')

    def test_catalog_ids_are_validated_and_deduplicated(self):
        from app.schemas import Preferences
        from pydantic import ValidationError
        self.assertEqual(Preferences(completed_course_ids=['cisco', 'cisco']).completed_course_ids, ['cisco'])
        with self.assertRaises(ValidationError):
            Preferences(completed_course_ids=['unverified-unknown-id'])
