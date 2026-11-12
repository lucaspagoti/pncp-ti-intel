"""Casos compartilhados pelos testes do PRODERJ (ADR 0042)."""

# Todas as grafias vistas no site e no CSV do SIGA para o mesmo número de processo.
CASOS_PROCESSO = [
    ("SEI-430002/000030/2024", "430002/30/2024"),
    ("SEI - 430002/000030/2024 - MICROSOFT", "430002/30/2024"),
    ("PROCESSO SEI nº SEI-430002/000719/2024 - STORAGE", "430002/719/2024"),
    ("430002/001509/2024", "430002/1509/2024"),
    ("SEI-430002/001112//2024", "430002/1112/2024"),
    ("SEI-430002/0001597/2024", "430002/1597/2024"),
    ("SEI - 430002 / 30 / 2024", "430002/30/2024"),
    ("SEI - 120211/001283/2020 - AQUISIÇÃO", None),  # outro órgão
    ("430002/000000/2024", None),
    ("sem processo", None),
    ("", None),
    (None, None),
]
