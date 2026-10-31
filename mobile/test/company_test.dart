import 'package:flutter_test/flutter_test.dart';
import 'package:vagou/company.dart';
void main() {
  test('accepts formatted, clean and alphanumeric CNPJ', () {
    for (final value in ['11.222.333/0001-81', '11222333000181', ' 11.222.333 / 0001 - 81 ', '12abc34501DE35']) {
      expect(validCnpj(value), isTrue);
    }
    for (final value in ['11222333000182', '00000000000000', '11!222333000181']) {
      expect(validCnpj(value), isFalse);
    }
  });
}
