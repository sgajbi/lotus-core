from pathlib import Path

from scripts import config_access_guard, no_alias_contract_guard


def test_config_access_guard_ignores_generated_build_artifacts() -> None:
    generated_path = Path("src/services/query_service/build/lib/app/settings.py")
    source_path = Path("src/services/query_service/app/settings.py")

    assert config_access_guard._is_generated_artifact(generated_path) is True
    assert config_access_guard._is_generated_artifact(source_path) is False


def test_no_alias_contract_guard_ignores_generated_build_artifacts() -> None:
    generated_path = Path("src/services/query_service/build/lib/app/contracts.py")
    source_path = Path("src/services/query_service/app/contracts.py")

    assert no_alias_contract_guard._is_exempt(generated_path) is True
    assert no_alias_contract_guard._is_exempt(source_path) is False
