import pytest

from agente.skills import PASTA_SKILLS, carregar_skill, catalogo, catalogo_texto, conteudo_skill, ler_skill


def escrever(pasta, nome, texto):
    (pasta / nome).mkdir()
    (pasta / nome / "SKILL.md").write_text(texto, encoding="utf-8")


def test_catalogo_le_nome_e_descricao(tmp_path):
    escrever(tmp_path, "b", "---\nname: b\ndescription: Faz B.\n---\n# B\npassos")
    escrever(tmp_path, "a", "---\nname: a\ndescription: >\n  Faz A\n  em duas linhas.\n---\n# A")
    assert catalogo(tmp_path) == [
        {"nome": "a", "descricao": "Faz A em duas linhas."},
        {"nome": "b", "descricao": "Faz B."},
    ]
    assert catalogo_texto(tmp_path) == "- a: Faz A em duas linhas.\n- b: Faz B."


def test_catalogo_nao_inclui_corpo(tmp_path):
    escrever(tmp_path, "a", "---\nname: a\ndescription: Faz A.\n---\nSEGREDO DO CORPO")
    assert "SEGREDO" not in catalogo_texto(tmp_path)


def test_conteudo_devolve_corpo_sem_frontmatter(tmp_path):
    escrever(tmp_path, "a", "---\nname: a\ndescription: Faz A.\n---\n# A\n1. passo")
    assert conteudo_skill("a", tmp_path) == "# A\n1. passo"


def test_skill_inexistente_lista_as_validas(tmp_path):
    escrever(tmp_path, "a", "---\nname: a\ndescription: Faz A.\n---\nx")
    escrever(tmp_path, "b", "---\nname: b\ndescription: Faz B.\n---\ny")
    resposta = conteudo_skill("c", tmp_path)
    assert "não existe" in resposta and "a, b" in resposta


def test_frontmatter_sem_description_e_rejeitado(tmp_path):
    escrever(tmp_path, "a", "---\nname: a\n---\nx")
    with pytest.raises(ValueError):
        ler_skill(tmp_path / "a" / "SKILL.md")


def test_skills_do_projeto():
    nomes = [s["nome"] for s in catalogo()]
    assert nomes == ["circuito-para-placa", "prototipar-circuito"]
    for caminho in PASTA_SKILLS.glob("*/SKILL.md"):
        meta, _ = ler_skill(caminho)
        assert meta["name"] == caminho.parent.name  # nome da pasta = nome da skill


def test_ferramenta_carregar_skill():
    texto = carregar_skill.invoke({"nome": "prototipar-circuito"})
    for etapa in ["buscar_documentos", "validar_diagrama", "salvar_projeto", "compilar",
                  "wokwi_start_simulation", "wokwi_read_serial", "board-esp32-devkit-c-v4"]:
        assert etapa in texto
    assert "não existe" in carregar_skill.invoke({"nome": "inexistente"})
