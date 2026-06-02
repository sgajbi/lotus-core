from scripts import maintainability_gate as gate


def test_maintainability_violations_accepts_a_through_c_modules() -> None:
    report = {
        "src/a.py": {"mi": 100.0, "rank": "A"},
        "src/b.py": {"mi": 15.0, "rank": "B"},
        "src/c.py": {"mi": 1.0, "rank": "C"},
    }

    assert gate.maintainability_violations(report) == []


def test_maintainability_violations_rejects_d_or_worse_modules() -> None:
    report = {
        "src/bad.py": {"mi": -1.0, "rank": "D"},
        "src/worse.py": {"mi": -5.0, "rank": "F"},
    }

    assert gate.maintainability_violations(report) == [
        "src/bad.py: maintainability rank D (-1.00) exceeds C",
        "src/worse.py: maintainability rank F (-5.00) exceeds C",
    ]
