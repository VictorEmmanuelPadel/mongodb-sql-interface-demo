"""Demo instructions written locally and onto the Windows desktop."""

from __future__ import annotations

import re

from sql_demo.config import Config


def sql_ident(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return '"' + name.replace('"', '""') + '"'


def sample_sql(database: str, collections: list[str]) -> str:
    lines = [
        f"-- MongoDB SQL Interface queries for database {database}",
        "-- The SQL Interface is read-only. Column names follow the generated schema.",
        "",
    ]
    if database == "sample_mflix" and (not collections or "movies" in collections):
        lines.extend(
            [
                "SELECT title, year, runtime",
                "FROM movies",
                "WHERE year = 2015",
                "LIMIT 25;",
                "",
                "SELECT year, COUNT(*) AS films",
                "FROM movies",
                "WHERE year IS NOT NULL",
                "GROUP BY year",
                "ORDER BY year DESC",
                "LIMIT 30;",
                "",
            ]
        )
    for collection in collections:
        if collection == "movies" and database == "sample_mflix":
            continue
        lines.extend(
            [
                "SELECT *",
                f"FROM {sql_ident(collection)}",
                "LIMIT 25;",
                "",
            ]
        )
    if not collections:
        lines.extend(
            [
                "SELECT *",
                "FROM <collection>",
                "LIMIT 25;",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_guide(
    config: Config,
    *,
    host: str,
    power_bi_uri: str,
    vm_public_ip: str,
    schemas: list[dict],
) -> str:
    collections = [
        str(row["collection"])
        for row in schemas
        if row.get("database") == config.primary_database and row.get("collection")
    ]
    schema_lines = ["Schemas written to __sql_schemas:"]
    if schemas:
        for row in schemas:
            flag = " unstable" if row.get("unstable") else ""
            schema_lines.append(f"  - {row['database']}.{row['collection']}{flag}")
    else:
        schema_lines.append("  - none yet. Run setup again without --skip-schema.")

    rdp = (
        f"Public IP: {vm_public_ip}\n"
        f"Windows user: {config.vm_admin_username}\n"
        f"Windows password: {config.vm_admin_password}\n"
        "From a Mac, add this PC in Windows App. From Windows, run mstsc."
        if vm_public_ip
        else "No Azure VM was created for this run."
    )
    return f"""MongoDB SQL Interface demo
Dedicated Atlas cluster: {config.atlas_cluster_name}
Database: {config.primary_database}

This VM has Power BI Desktop, the MongoDB ODBC driver, and the Power BI connector.
The SQL Interface is read-only.

{chr(10).join(schema_lines)}

Connect from Power BI Desktop
1. Open Power BI Desktop from the desktop shortcut.
2. Choose Get data, then search for MongoDB.
3. Select MongoDB Atlas SQL and choose Connect.
4. MongoDB URI (do not put a username or password in the URI):
   {power_bi_uri}
5. Database:
   {config.primary_database}
6. Leave the native query empty for the first connection, then choose Import.
   DirectQuery is available with the installed ODBC driver when you want live queries.
7. Sign in with:
   Username: {config.sql_username}
   Password: {config.sql_password}
8. Expand the database and load one of the collections listed above.

The username and password belong to a database user created for this demo.
That user can read {", ".join(config.databases)} and can update __sql_schemas.
It also has read on __mdb_internal_sqlinterface, which the schema builder requires.

Cluster host: {host}

RDP
{rdp}

Regenerate schemas on this VM
C:\\SQLInterfaceDemo\\mongodb-schema-manager.exe
Use the same username and password. Include --ns-include {config.schema_ns_include[0]}

Sample queries are in C:\\SQLInterfaceDemo\\sample-queries.sql.

Docs
https://www.mongodb.com/docs/sql-interface/
https://www.mongodb.com/docs/sql-interface/connect/
"""
