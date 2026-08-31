"""Canonical database text expressions shared by persistence models."""

PYTHON_STRIP_WHITESPACE_SQL = (
    r"U&' \0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680"
    r"\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028"
    r"\2029\202F\205F\3000'"
)

CANONICAL_TENANT_ID_CHECK_SQL = (
    f"tenant_id = btrim(tenant_id, {PYTHON_STRIP_WHITESPACE_SQL}) AND tenant_id <> ''"
)
