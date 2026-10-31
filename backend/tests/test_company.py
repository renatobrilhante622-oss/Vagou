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

    def test_known_cnpjs_keep_leading_zeroes_and_pasted_masks(self):
        values = [
            ('04.252.011/0001-10', '04252011000110'),
            ('00.000.000/0001-91', '00000000000191'),
            ('\u00a004.252.011 / 0001\u201110\u202f', '04252011000110'),
            ('11 . 222 . 333 / 0001 \u2013 81', '11222333000181'),
        ]
        from app.company import normalize_cnpj
        for masked, canonical in values:
            with self.subTest(masked=masked):
                self.assertEqual(normalize_cnpj(masked), canonical)
                self.assertTrue(valid_cnpj(masked))
                self.assertTrue(valid_cnpj(canonical))

    def test_format_tolerance_never_bypasses_checksum_or_type(self):
        for value in ['04.252.011/0001-11', '11.222.333/0001-82', '04!252011000110', None, 4252011000110]:
            with self.subTest(value=value):
                self.assertFalse(valid_cnpj(value))
