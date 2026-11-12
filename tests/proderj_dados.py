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
    # Espaços Unicode (QA-W10-01): SQL e Python têm de concordar, aceitando os mesmos.
    ("SEI-430002\u2003/000030/2024", "430002/30/2024"),
    ("SEI-430002\u00a0/\u00a0000030/2024", "430002/30/2024"),
    ("SEI-430002\u2009/\u300030/2024", "430002/30/2024"),
    ("SEI-430002\u2028/000030/2024", "430002/30/2024"),
    ("SEI-430002\u200b/000030/2024", None),  # espaço de largura zero não é espaço
    ("SEI-430002/\u0663\u0660/2024", None),  # dígito árabe-índico não é dígito aqui
    ("SEI - 120211/001283/2020 - AQUISIÇÃO", None),  # outro órgão
    ("430002/000000/2024", None),
    ("sem processo", None),
    ("", None),
    (None, None),
]
