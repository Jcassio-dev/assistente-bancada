import pytest

from agente.rag import PASTA_INDICE

pytestmark = pytest.mark.skipif(not PASTA_INDICE.exists(), reason="índice não gerado (scripts/indexar.py)")


def test_mensagem_tem_catalogo_documentos_e_regras():
    from agente.prompts import mensagem_sistema
    from agente.rag import documentos_indexados

    m = mensagem_sistema()
    assert "{" not in m  # nenhum campo do format sobrou
    assert "- prototipar-circuito:" in m and "- circuito-para-placa:" in m
    assert "Montar e testar um circuito" in m
    assert "# Prototipar um circuito" not in m  # o corpo da skill não entra, só o catálogo
    for doc in documentos_indexados():
        assert f"`{doc}`" in m
    for regra in ["em inglês", "reformule e busque de novo", "Nunca invente valores", "só com ESP32"]:
        assert regra in m
