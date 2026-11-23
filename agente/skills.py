from pathlib import Path

import yaml
from langchain_core.tools import tool

PASTA_SKILLS = Path(__file__).resolve().parent.parent / "skills"


def ler_skill(caminho):
    texto = caminho.read_text(encoding="utf-8")
    if not texto.startswith("---"):
        raise ValueError(f"{caminho} não começa com frontmatter (---)")
    _, frontmatter, corpo = texto.split("---", 2)
    meta = yaml.safe_load(frontmatter)
    if not meta or not meta.get("name") or not meta.get("description"):
        raise ValueError(f"{caminho} precisa de name e description no frontmatter")
    return meta, corpo.strip()


def catalogo(pasta=PASTA_SKILLS):
    itens = []
    for caminho in sorted(pasta.glob("*/SKILL.md")):
        meta, _ = ler_skill(caminho)
        itens.append({"nome": meta["name"], "descricao": " ".join(meta["description"].split())})
    return itens


def catalogo_texto(pasta=PASTA_SKILLS):
    return "\n".join(f"- {s['nome']}: {s['descricao']}" for s in catalogo(pasta))


def conteudo_skill(nome, pasta=PASTA_SKILLS):
    for caminho in sorted(pasta.glob("*/SKILL.md")):
        meta, corpo = ler_skill(caminho)
        if meta["name"] == nome:
            return corpo
    validos = ", ".join(s["nome"] for s in catalogo(pasta))
    return f"Skill '{nome}' não existe. Skills disponíveis: {validos}."


@tool
def carregar_skill(nome: str) -> str:
    """Carrega as instruções completas de uma skill do catálogo.

    Chame antes de começar uma tarefa que uma skill cobre e siga as etapas dela.
    """
    return conteudo_skill(nome)
