from pathlib import Path

from sql_demo.vm_guide import sample_sql


def test_sample_sql_includes_movies_for_sample_mflix() -> None:
    sql = sample_sql("sample_mflix", ["movies", "comments"])
    assert "FROM movies" in sql
    assert "FROM comments" in sql
    assert "GROUP BY year" in sql


def test_vm_install_script_has_no_terraform_interpolation() -> None:
    script = Path("terraform/scripts/install-demo-tools.ps1").read_text(encoding="utf-8")
    assert "${" not in script
    assert "https://aka.ms/vc14/vc_redist.x64.exe" in script
    assert "$env:ODBC_URL" in script
    assert "PBIDesktopSetup_x64.exe" in script
    assert "$env:CONNECTOR_URL" in script
    assert "New-Item -ItemType Directory -Force -Path $connectorDir" in script
    assert "Microsoft Power BI Desktop\\Custom Connectors" not in script
    assert "Public\\Documents" not in script
