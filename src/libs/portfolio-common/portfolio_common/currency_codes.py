def normalize_currency_code(currency_code: object) -> str:
    if not isinstance(currency_code, str):
        raise ValueError("Currency code must be a string.")

    normalized = currency_code.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency code must be a three-letter ISO 4217 code.")
    return normalized


def normalize_optional_currency_code(currency_code: object) -> str | None:
    if currency_code is None:
        return None
    return normalize_currency_code(currency_code)
