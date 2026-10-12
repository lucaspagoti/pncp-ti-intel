"""Conninfo e URL preservam senhas sem interpretar caracteres de URL/INI/shell."""

from dataclasses import replace

import pytest
from psycopg.conninfo import conninfo_to_dict

from pncp_ti.config import admin_dsn, admin_url, get_settings, ingest_dsn


@pytest.mark.parametrize("password", ["a@:/?#%$&'\\ b", "100%ready", "${HOME}$(id)`id`"])
def test_password_roundtrip(password):
    settings = replace(
        get_settings(),
        postgres_admin_password=password,
        ingest_password=password,
        postgres_db="database with space",
    )
    for builder in (admin_dsn, ingest_dsn):
        values = conninfo_to_dict(builder(settings))
        assert values["password"] == password
        assert values["dbname"] == settings.postgres_db
    url = admin_url(settings)
    assert url.password == password
    assert url.database == settings.postgres_db
    assert url.drivername == "postgresql+psycopg"
