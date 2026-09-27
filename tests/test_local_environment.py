from pathlib import Path

import pytest

import config


def test_enabling_observability_without_an_admin_token_refuses_to_start() -> None:
    with pytest.raises(ValueError, match="DEVELOPMENT_OBSERVABILITY_TOKEN"):
        config.validate_observability_settings(enabled=True, token="")


@pytest.mark.parametrize(("enabled", "token"), [(False, ""), (False, "x"), (True, "secret")])
def test_observability_settings_accept_disabled_or_token_protected(enabled, token) -> None:
    config.validate_observability_settings(enabled=enabled, token=token)


def test_local_dotenv_supplies_a_missing_environment_value(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    key = "EI_LOCAL_DOTENV_TEST_VALUE"
    secret = "local-test-value-not-a-production-secret"
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(f"{key}={secret}\n", encoding="utf-8")
    monkeypatch.delenv(key, raising=False)

    config.load_project_dotenv(dotenv_path)

    assert config.os.environ[key] == secret
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_environment_value_overrides_local_dotenv(monkeypatch, tmp_path: Path) -> None:
    key = "EI_LOCAL_DOTENV_OVERRIDE_TEST_VALUE"
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(f"{key}=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv(key, "from-environment")

    config.load_project_dotenv(dotenv_path)

    assert config.os.environ[key] == "from-environment"
