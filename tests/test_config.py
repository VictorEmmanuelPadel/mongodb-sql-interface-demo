import pytest

from sql_demo.config import Config, ConfigError, generate_password, resolve_password


def _env(**overrides: str) -> dict[str, str]:
    env = {
        "ATLAS_PROJECT_ID": "abc123abc123abc123abc123",
        "ATLAS_CLUSTER_NAME": "Cluster0",
        "ATLAS_DATABASE": "sample_mflix",
    }
    env.update(overrides)
    return env


def test_config_accepts_a_complete_env() -> None:
    config = Config.from_mapping(_env())
    assert config.primary_database == "sample_mflix"
    assert config.schema_ns_include == ("sample_mflix.*",)
    assert config.sql_username == "sql-demo"
    assert config.vm_admin_username == "sqlInterfaceDemo"
    assert config.azure_location == "eastus"
    assert config.sql_password == ""
    assert config.vm_admin_password == ""


def test_config_accepts_passwords_and_region() -> None:
    config = Config.from_mapping(
        _env(
            SQL_PASSWORD="sql-secret",
            VM_ADMIN_PASSWORD="Demo-Password1",
            AZURE_LOCATION="westus2",
        )
    )
    assert config.sql_password == "sql-secret"
    assert config.vm_admin_password == "Demo-Password1"
    assert config.azure_location == "westus2"


def test_config_splits_databases_and_patterns() -> None:
    config = Config.from_mapping(
        _env(ATLAS_DATABASE="sample_mflix, sample_airbnb"),
    )
    assert config.databases == ("sample_mflix", "sample_airbnb")
    assert config.schema_ns_include == ("sample_mflix.*", "sample_airbnb.*")


def test_config_rejects_a_short_project_id() -> None:
    with pytest.raises(ConfigError, match="ATLAS_PROJECT_ID"):
        Config.from_mapping(_env(ATLAS_PROJECT_ID="1234"))


def test_config_does_not_require_azure_values() -> None:
    config = Config.from_mapping(_env())
    assert config.atlas_cluster_name == "Cluster0"


def test_config_accepts_custom_usernames() -> None:
    config = Config.from_mapping(_env(SQL_USERNAME="powerbi", VM_ADMIN_USERNAME="demoadmin"))
    assert config.sql_username == "powerbi"
    assert config.vm_admin_username == "demoadmin"


def test_config_rejects_a_reserved_windows_username() -> None:
    with pytest.raises(ConfigError, match="VM_ADMIN_USERNAME"):
        Config.from_mapping(_env(VM_ADMIN_USERNAME="admin"))


def test_config_rejects_a_weak_windows_password() -> None:
    with pytest.raises(ConfigError, match="VM_ADMIN_PASSWORD"):
        Config.from_mapping(_env(VM_ADMIN_PASSWORD="password"))


def test_config_rejects_a_display_region_name() -> None:
    with pytest.raises(ConfigError, match="AZURE_LOCATION"):
        Config.from_mapping(_env(AZURE_LOCATION="East US"))


def test_supplied_password_is_kept() -> None:
    assert resolve_password("chosen-secret") == "chosen-secret"


def test_blank_password_is_generated() -> None:
    password = resolve_password("")
    assert len(password) >= 12


def test_generated_password_has_mixed_characters() -> None:
    password = generate_password()
    assert any(char.islower() for char in password)
    assert any(char.isupper() for char in password)
    assert any(char.isdigit() for char in password)
