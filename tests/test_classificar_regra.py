"""Um caso por ramo de `classificar_por_regra` (ADR 0006, camada 1)."""

from __future__ import annotations

import pytest

from pncp_ti.classificar.regra import PredicaoTI, classificar_por_regra


def test_catmat_grupo_70_e_ti():
    item = {
        "material_ou_servico": "M",
        "codigo_grupo": 70,
        "codigo_classe": 7010,
        "codigo_item_catalogo": 1,
        "descricao_resumida": "Cabo elétrico flexível",
    }
    assert classificar_por_regra(item) == PredicaoTI.TI


def test_catser_classe_de_software_e_ti():
    item = {
        "material_ou_servico": "S",
        "codigo_grupo": None,
        "codigo_classe": 1611,
        "codigo_item_catalogo": 1,
        "descricao_resumida": "Serviço de instalação",
    }
    assert classificar_por_regra(item) == PredicaoTI.TI


def test_catalogo_conhecido_fora_da_lista_e_nao_ti():
    item = {
        "material_ou_servico": "M",
        "codigo_grupo": 85,
        "codigo_classe": 8510,
        "codigo_item_catalogo": 1,
        "descricao_resumida": "Arroz tipo 1",
    }
    assert classificar_por_regra(item) == PredicaoTI.NAO_TI


def test_telefonia_pendente_nao_e_decidida_por_palavra_chave():
    # Decisão de projeto: catálogo primeiro, não se mistura com palavra-chave.
    item = {
        "material_ou_servico": "S",
        "codigo_grupo": 841,
        "codigo_classe": 8411,
        "codigo_item_catalogo": 1,
        "descricao_resumida": "Serviço de provedor com licença de software incluída",
    }
    assert classificar_por_regra(item) == PredicaoTI.INDEFINIDO


def test_sem_catalogo_com_palavra_chave_e_ti():
    item = {
        "material_ou_servico": None,
        "codigo_grupo": None,
        "codigo_classe": None,
        "codigo_item_catalogo": None,
        "descricao_resumida": "Licença de Software antivírus corporativo",
    }
    assert classificar_por_regra(item) == PredicaoTI.TI


def test_sem_catalogo_e_sem_palavra_chave_e_indefinido():
    item = {
        "material_ou_servico": None,
        "codigo_grupo": None,
        "codigo_classe": None,
        "codigo_item_catalogo": None,
        "descricao_resumida": "Serviço de manutenção predial",
    }
    assert classificar_por_regra(item) == PredicaoTI.INDEFINIDO


def test_codigo_item_catalogo_sem_grupo_ou_classe_nao_decide_por_catalogo():
    # Achado da revisão: `codigo_item_catalogo` presente mas `codigo_grupo`
    # (o campo que a decisão de material realmente usa) nulo não pode virar
    # NAO_TI com confiança — cai pra palavra-chave, igual a não ter catálogo.
    item = {
        "material_ou_servico": "M",
        "codigo_grupo": None,
        "codigo_classe": None,
        "codigo_item_catalogo": 999,
        "descricao_resumida": "Licença de software de gestão",
    }
    assert classificar_por_regra(item) == PredicaoTI.TI


def test_codigo_item_catalogo_sem_grupo_e_sem_palavra_chave_e_indefinido():
    item = {
        "material_ou_servico": "M",
        "codigo_grupo": None,
        "codigo_classe": None,
        "codigo_item_catalogo": 999,
        "descricao_resumida": "Peça sobressalente genérica",
    }
    assert classificar_por_regra(item) == PredicaoTI.INDEFINIDO


def test_sem_descricao_nenhuma_e_indefinido():
    item = {
        "material_ou_servico": None,
        "codigo_grupo": None,
        "codigo_classe": None,
        "codigo_item_catalogo": None,
        "descricao_resumida": None,
        "descricao_detalhada": None,
    }
    assert classificar_por_regra(item) == PredicaoTI.INDEFINIDO


@pytest.mark.parametrize(
    "classe", [1411, 1412, 1413, 1414, 8411, 8412, 8413, 8414, 8415, 8416, 8417, 8421, 8422]
)
def test_telefonia_internet_aguardam_rotulagem(classe):
    assert (
        classificar_por_regra({"material_ou_servico": "S", "codigo_classe": classe})
        == PredicaoTI.INDEFINIDO
    )


@pytest.mark.parametrize("valor", [0, -1, True, "0"])
@pytest.mark.parametrize("material,campo", [("M", "codigo_grupo"), ("S", "codigo_classe")])
def test_catalogo_invalido_nao_exclui_ti(valor, material, campo):
    assert (
        classificar_por_regra(
            {
                "material_ou_servico": material,
                campo: valor,
                "descricao_resumida": "Licença de software",
            }
        )
        == PredicaoTI.TI
    )
