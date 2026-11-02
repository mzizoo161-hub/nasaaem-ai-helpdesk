"""
Nasaaem AI Helpdesk - Supabase PostgreSQL connection.

Reads DATABASE_URL from the environment or local
Streamlit secrets. Does not print credentials.
"""

import os
import tomllib
from pathlib import Path

import psycopg




def get_app_connection():
    """
    Connect to Supabase using the restricted
    nasaaem_app database role.

    Intended for trusted server-side use only.
    """

    import streamlit as st

    url = os.getenv("APP_DATABASE_URL")

    if not url:
        secrets_path = (
            Path(__file__).resolve().parent
            / ".streamlit"
            / "secrets.toml"
        )

        if secrets_path.is_file():
            with secrets_path.open("rb") as file:
                config = tomllib.load(file)

            url = config.get("APP_DATABASE_URL")

    if not url:
        try:
            url = st.secrets.get("APP_DATABASE_URL")
        except FileNotFoundError:
            pass

    if not url:
        raise RuntimeError(
            "APP_DATABASE_URL is not configured."
        )

    return psycopg.connect(
        url,
        sslmode="require",
        connect_timeout=10,
        prepare_threshold=None,
    )

if __name__ == "__main__":

    print("=== NASAAEM CLOUD DATABASE CHECK ===")

    with get_cloud_connection() as connection:

        rows = connection.execute(
            """
            SELECT
                table_schema,
                table_name

            FROM information_schema.tables

            WHERE table_schema IN (
                'employees',
                'helpdesk'
            )

            AND table_type = 'BASE TABLE'

            ORDER BY
                table_schema,
                table_name
            """
        ).fetchall()

        for schema, table in rows:
            print(f"{schema}.{table}")

        print("TABLES FOUND:", len(rows))
        print(
            "STATUS:",
            "PASS" if len(rows) == 4 else "CHECK"
        )
