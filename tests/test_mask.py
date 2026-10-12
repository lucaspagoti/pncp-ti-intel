"""CPF sempre mascarado (regra fixa do CLAUDE.md) — inclusive quando o dígito
não bate 11 (ex.: zero à esquerda perdido na origem), que era o bug real: a
condição antiga `(tipo_pessoa == "PF" or len == 11) and len == 11` nunca
deixava `tipo_pessoa` decidir nada.
"""

from pncp_ti.mask import mascarar_ni


def test_cpf_de_11_digitos_e_mascarado():
    assert mascarar_ni("12345678901", "PF") == "123******01"


def test_cpf_pf_com_menos_de_11_digitos_ainda_e_mascarado():
    # Zero à esquerda perdido (API devolveu como inteiro) — tipo_pessoa é o
    # único sinal confiável aqui, e tem que bastar.
    assert mascarar_ni("1234567890", "PF") == "123*****90"


def test_cnpj_passa_direto():
    assert mascarar_ni("12345678000190", "PJ") == "12345678000190"


def test_none_e_vazio_retornam_none():
    assert mascarar_ni(None, "PF") is None
    assert mascarar_ni("", "PF") is None
