"""Canonical SQL text-normalization expressions shared by ORM constraints."""

PYTHON_STRIP_BOUNDARY_SQL = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)
PYTHON_ISO_DATE_TEXT_VALID_SQL = (
    "pg_input_is_valid(payload->>'earliest_impacted_date', 'date') IS TRUE "
    "AND payload->>'earliest_impacted_date' ~ "
    r"'^(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{8}|"
    r"[0-9]{4}-W[0-9]{2}(?:-[1-7])?|[0-9]{4}W[0-9]{2}[1-7]?)$'"
)
PYTHON_ISO_DATETIME_WITH_TIMEZONE_PATTERN_SQL = (
    r"'^[0-9]{4}-?[0-9]{2}-?[0-9]{2}[T ]"
    r"([0-9]{2}:[0-9]{2}(:[0-9]{2}([.,][0-9]+)?)?|"
    r"[0-9]{4}([0-9]{2}([.,][0-9]+)?)?)"
    r"(Z|[+-]([0-9]{2}|[0-9]{2}:[0-9]{2}(:[0-9]{2}([.,][0-9]+)?)?|"
    r"[0-9]{4}([0-9]{2}([.,][0-9]+)?)?))$'"
)
