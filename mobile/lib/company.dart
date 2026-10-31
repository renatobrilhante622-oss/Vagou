String normalizeCnpj(String value) => value.replaceAll(RegExp(r'[.\s/\-\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\u2010-\u2015\u2212]'), '').toUpperCase();

bool validCnpj(String input) {
  final value = normalizeCnpj(input);
  if (!RegExp(r'^[A-Z0-9]{12}[0-9]{2}$').hasMatch(value) || value.split('').toSet().length == 1) return false;
  final digits = value.codeUnits.map((c) => c - 48).toList();
  const weights = [[5,4,3,2,9,8,7,6,5,4,3,2], [6,5,4,3,2,9,8,7,6,5,4,3,2]];
  for (var step = 0; step < 2; step++) {
    var sum = 0;
    for (var i = 0; i < weights[step].length; i++) { sum += digits[i] * weights[step][i]; }
    final remainder = sum % 11;
    if (digits[12 + step] != (remainder < 2 ? 0 : 11 - remainder)) return false;
  }
  return true;
}
