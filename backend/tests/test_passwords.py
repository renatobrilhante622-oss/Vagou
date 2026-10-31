import unittest
from app.passwords import hash_password, verify_password


class PasswordTests(unittest.TestCase):
    def test_round_trip_and_wrong_password(self):
        stored = hash_password('UmaSenhaÚnicaMuitoLonga!')
        self.assertTrue(verify_password('UmaSenhaÚnicaMuitoLonga!', stored))
        self.assertFalse(verify_password('OutraSenha', stored))
        self.assertNotIn('UmaSenha', stored)

    def test_individual_salts(self):
        self.assertNotEqual(hash_password('same password'), hash_password('same password'))

    def test_corrupt_or_unsupported_hash(self):
        for stored in ['', 'plain$password', 'other$eA==$eA==', 'scrypt$!$!']:
            with self.subTest(stored=stored):
                self.assertFalse(verify_password('password', stored))
