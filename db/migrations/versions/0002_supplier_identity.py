"""Identidade de fornecedor separada da máscara e limpeza de CPF legado (ADR 0013)."""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _redact(value):
    # Implementação congelada na migração; não depende de mapeador futuro.
    if isinstance(value, dict):
        result = {k: _redact(v) for k, v in value.items()}
        for name, original in value.items():
            if "cpf" in name.lower() and isinstance(original, (str, int)):
                text = str(original)
                if "*" not in text:
                    digits = "".join(c for c in text if c.isdigit())
                    result[name] = (
                        digits[:3] + "*" * (len(digits) - 5) + digits[-2:]
                        if len(digits) > 5
                        else "*" * len(digits)
                    )
        for field, kind in (
            ("niFornecedor", "tipoPessoa"),
            ("niFornecedorSubContratado", "tipoPessoaSubContratada"),
        ):
            original = value.get(field)
            if original is not None and value.get(kind) == "PF" and "*" not in str(original):
                digits = "".join(c for c in str(original) if c.isdigit())
                result[field] = (
                    digits[:3] + "*" * (len(digits) - 5) + digits[-2:]
                    if len(digits) > 5
                    else "*" * len(digits)
                )
        return result
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(
            r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)",
            lambda m: (
                re.sub(r"\D", "", m.group())[:3] + "******" + re.sub(r"\D", "", m.group())[-2:]
            ),
            value,
        )
    return value


def upgrade():
    op.execute("ALTER TABLE contratos DROP CONSTRAINT contratos_ni_fornecedor_fkey")
    op.execute("ALTER TABLE fornecedores ADD COLUMN fornecedor_id text")
    op.execute(
        "UPDATE fornecedores SET fornecedor_id = CASE "
        "WHEN tipo_pessoa = 'PJ' AND ni ~ '^[0-9]{14}$' THEN 'cnpj:' || ni "
        "ELSE 'legacy:' || gen_random_uuid()::text END"
    )
    op.execute("ALTER TABLE fornecedores DROP CONSTRAINT fornecedores_pkey")
    op.execute("ALTER TABLE fornecedores ADD PRIMARY KEY (fornecedor_id)")
    op.execute("ALTER TABLE contratos ADD COLUMN fornecedor_id text")
    # PF legado pode ter sofrido colisão: não inventar vínculo que não se pode recuperar.
    op.execute(
        "UPDATE contratos c SET fornecedor_id = f.fornecedor_id "
        "FROM fornecedores f WHERE c.ni_fornecedor = f.ni "
        "AND f.fornecedor_id LIKE 'cnpj:%'"
    )
    op.execute(
        "ALTER TABLE contratos ADD CONSTRAINT contratos_fornecedor_id_fkey "
        "FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(fornecedor_id)"
    )
    op.execute("CREATE INDEX ix_contratos_fornecedor_id ON contratos (fornecedor_id)")

    bind = op.get_bind()
    for name, key in (
        ("contratacoes", "numero_controle_pncp"),
        ("atas", "numero_controle_pncp_ata"),
        ("contratos", "numero_controle_pncp"),
        ("orgaos", "cnpj"),
        ("fornecedores", "fornecedor_id"),
    ):
        table = sa.Table(name, sa.MetaData(), autoload_with=bind)
        cursor = bind.execute(sa.select(table))
        while batch := cursor.fetchmany(500):
            for row in batch:
                values = dict(row._mapping)
                changes = {}
                for col in table.columns:
                    if col.name == key or col.name == "fornecedor_id":
                        continue
                    old = values[col.name]
                    if isinstance(col.type, (sa.String, JSONB)):
                        new = _redact(old)
                        if new != old:
                            changes[col.name] = new
                if name == "fornecedores" and values.get("tipo_pessoa") == "PF":
                    changes["ni"] = _redact({"cpf": values["ni"]})["cpf"]
                if name == "contratos" and (values.get("raw") or {}).get("tipoPessoa") == "PF":
                    changes["ni_fornecedor"] = _redact({"cpf": values["ni_fornecedor"]})["cpf"]
                if changes:
                    bind.execute(
                        table.update().where(table.c[key] == values[key]).values(**changes)
                    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT 1 FROM fornecedores GROUP BY ni HAVING count(*) > 1 LIMIT 1")
    ).first():
        raise RuntimeError(
            "Downgrade recusado: máscaras duplicadas perderiam identidade (ADR 0013)"
        )
    op.execute("DROP INDEX ix_contratos_fornecedor_id")
    op.execute("ALTER TABLE contratos DROP CONSTRAINT contratos_fornecedor_id_fkey")
    op.execute("ALTER TABLE contratos DROP COLUMN fornecedor_id")
    op.execute("ALTER TABLE fornecedores DROP CONSTRAINT fornecedores_pkey")
    op.execute("ALTER TABLE fornecedores DROP COLUMN fornecedor_id")
    op.execute("ALTER TABLE fornecedores ADD PRIMARY KEY (ni)")
    op.execute(
        "ALTER TABLE contratos ADD CONSTRAINT contratos_ni_fornecedor_fkey "
        "FOREIGN KEY (ni_fornecedor) REFERENCES fornecedores(ni)"
    )
