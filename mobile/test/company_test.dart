import 'package:flutter_test/flutter_test.dart';
import 'package:vagou/company.dart';
void main() {
  test('accepts formatted, clean and alphanumeric CNPJ', () {
    for (final value in ['11.222.333/0001-81', '11222333000181', ' 11.222.333 / 0001 - 81 ', '12abc34501DE35', '04.252.011/0001-10', '04252011000110', '00.000.000/0001-91', '\u00a004.252.011 / 0001\u201110\u202f', '11 . 222 . 333 / 0001 \u2013 81']) {
      expect(validCnpj(value), isTrue, reason: value);
      expect(normalizeCnpj(value).length, 14);
    }
    for (final value in ['11222333000182', '00000000000000', '11!222333000181', '04.252.011/0001-11']) {
      expect(validCnpj(value), isFalse);
    }
  });
}
