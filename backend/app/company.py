"""Canonical CNPJ parsing shared by Pydantic and checksum validation."""
import re

# Pasted masks may contain non-breaking spaces or typographic dashes. Only mask
# separators are ignored: arbitrary symbols must not repair an invalid identity.
_FORMATTING = re.compile(r'[.\s/\-\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\u2010-\u2015\u2212]')


def normalize_cnpj(value: str) -> str:
    return _FORMATTING.sub('', value).upper()


def valid_cnpj(value: str) -> bool:
    """Validate the Receita Federal numeric/alphanumeric checksum after parsing."""
    if not isinstance(value, str):
        return False
    value = normalize_cnpj(value)
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', value) or len(set(value)) == 1:
        return False
    numbers = [ord(character) - 48 for character in value]
    for length, weights in [(12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])]:
        remainder = sum(number * weight for number, weight in zip(numbers[:length], weights)) % 11
        if numbers[length] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True
