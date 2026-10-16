import base64
from pathlib import Path

from sql_demo.azure_run import _write_script
from sql_demo.config import Config
from sql_demo.vm_guide import render_guide, sample_sql


def _config() -> Config:
    return Config.from_mapping(
        {
            "ATLAS_PROJECT_ID": "abc123abc123abc123abc123",
            "ATLAS_CLUSTER_NAME": "Cluster0",
            "ATLAS_DATABASE": "sample_mflix",
        }
    )


def test_sample_sql_includes_movies_for_sample_mflix() -> None:
    sql = sample_sql("sample_mflix", ["movies", "comments"])
    assert "FROM movies" in sql
    assert "FROM comments" in sql
    assert "GROUP BY year" in sql


def test_guide_contains_the_connection_fields() -> None:
    config = _config()
    config = Config(
        atlas_project_id=config.atlas_project_id,
        atlas_cluster_name=config.atlas_cluster_name,
        databases=config.databases,
        sql_password="demo-secret",
        vm_admin_password="windows-secret",
    )
    guide = render_guide(
        config,
        host="cluster0.example.mongodb.net",
        power_bi_uri="mongodb+srv://cluster0.example.mongodb.net/?ssl=true&authSource=admin",
        vm_public_ip="203.0.113.20",
        schemas=[{"database": "sample_mflix", "collection": "movies", "unstable": False}],
    )
    assert "sql-demo" in guide
    assert "demo-secret" in guide
    assert "windows-secret" in guide
    assert "203.0.113.20" in guide
    assert "sample_mflix.movies" in guide


def test_vm_install_script_has_no_terraform_interpolation() -> None:
    script = Path("terraform/scripts/install-demo-tools.ps1").read_text(encoding="utf-8")
    assert "${" not in script
    assert "https://aka.ms/vc14/vc_redist.x64.exe" in script
    assert "https://downloads.mongodb.org/mongosql-odbc-driver/windows/3.0.0/release/mongoodbc-3.0.0.msi" in script
    assert "PBIDesktopSetup_x64.exe" in script
    assert "https://downloads.mongodb.org/mongo-powerbi-connector/MongoDBAtlasODBC-1.2.2.pqx" in script
    assert "New-Item -ItemType Directory -Force -Path $connectorDir" not in script


def test_vm_script_embeds_utf8_text() -> None:
    script = _write_script({r"C:\SQLInterfaceDemo\README.txt": "hello"})
    encoded = base64.b64encode(b"hello").decode("ascii")
    assert encoded in script
    assert r"C:\SQLInterfaceDemo\README.txt" in script
