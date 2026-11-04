"""Pooled Supabase connection for the isolated, synthetic-data prototype."""
import os
import tomllib
from pathlib import Path

import streamlit as st
from psycopg_pool import ConnectionPool


def _secret_url():
    url = os.environ.get('PROTOTYPE_DATABASE_URL')
    if not url:
        path = Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml'
        if path.is_file():
            with path.open('rb') as f:
                url = tomllib.load(f).get('PROTOTYPE_DATABASE_URL')
    if not url:
        try:
            url = st.secrets.get('PROTOTYPE_DATABASE_URL')
        except (FileNotFoundError, KeyError):
            pass
    if not url:
        raise RuntimeError('PROTOTYPE_DATABASE_URL is not configured')
    return url


@st.cache_resource(show_spinner=False)
def _pool(connection_string):
    # A reusable connection pool eliminates repeated DNS, TCP, TLS and
    # authentication work on every Streamlit button click/rerun.
    return ConnectionPool(
        conninfo=connection_string,
        min_size=0,
        max_size=5,
        max_idle=120,
        kwargs={
            'sslmode': 'require',
            'connect_timeout': 10,
            'prepare_threshold': None,
        },
        open=True,
    )


def get_prototype_connection():
    """Returns a context manager yielding a pooled psycopg connection."""
    return _pool(_secret_url()).connection()
