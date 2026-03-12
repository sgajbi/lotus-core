from portfolio_common.logging_utils import normalize_lineage_value


def test_normalize_lineage_value_converts_sentinels_to_none():
    assert normalize_lineage_value(None) is None
    assert normalize_lineage_value("") is None
    assert normalize_lineage_value("<not-set>") is None


def test_normalize_lineage_value_preserves_real_lineage():
    assert normalize_lineage_value("corr-123") == "corr-123"
