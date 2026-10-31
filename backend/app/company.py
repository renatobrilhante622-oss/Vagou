"""Brazilian CNPJ validation without transport or persistence dependencies."""
import re


def valid_cnpj(value: str) -> bool:
    """Receita Federal checksum, including alphanumeric CNPJs issued from 2026."""
    if not re.fullmatch(r'[A-Z0-9]{12}[0-9]{2}', value) or len(set(value)) == 1:
        return False
    numbers = [ord(character) - 48 for character in value]
    for length, weights in [(12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])]:
        remainder = sum(number * weight for number, weight in zip(numbers[:length], weights)) % 11
        if numbers[length] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True
