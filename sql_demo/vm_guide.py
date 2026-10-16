"""Sample SQL for the demo database."""

from __future__ import annotations

import re


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
