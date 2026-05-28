from portfolio_common.identifiers import normalize_lookup_identifier


def test_normalize_lookup_identifier_trims_source_identifier_without_case_change() -> None:
    assert normalize_lookup_identifier(" Sec_A ") == "Sec_A"


def test_normalize_lookup_identifier_maps_none_to_empty_lookup_key() -> None:
    assert normalize_lookup_identifier(None) == ""


def test_normalize_lookup_identifier_stringifies_non_string_values() -> None:
    assert normalize_lookup_identifier(12345) == "12345"
