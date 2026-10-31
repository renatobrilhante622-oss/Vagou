import unittest
from app.company import valid_cnpj


class CnpjChecks(unittest.TestCase):
    def test_valid_numeric(self):
        self.assertTrue(valid_cnpj('11222333000181'))
        self.assertTrue(valid_cnpj('00000000000191'))

    def test_new_alphanumeric_format(self):
        self.assertTrue(valid_cnpj('12ABC34501DE35'))
        self.assertFalse(valid_cnpj('12ABC34501DE36'))
        self.assertFalse(valid_cnpj('12ABCD00000100'))

    def test_invalid_shapes_and_check_digits(self):
        for value in ['', '00000000000000', '11222333000182', '1122233300018', 'AAAAAAAAAAAAAA']:
            with self.subTest(value=value):
                self.assertFalse(valid_cnpj(value))

    def test_masked_and_whitespace(self):
        for value in ['11.222.333/0001-81', ' 11.222.333 / 0001 - 81 ', '12abc34501DE35']:
            self.assertTrue(valid_cnpj(value))
        self.assertFalse(valid_cnpj('11!222333000181'))
