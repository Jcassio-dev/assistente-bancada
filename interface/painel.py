"""Dados da bancada: ligações, o que mudou entre versões e as telas capturadas.

O desenho da mesa fica em interface/mesa.py. As versões abaixo fixam as peças
(@wokwi/elements, MIT) e as placas (repositório wokwi-boards) carregadas por CDN.
"""

import base64
from pathlib import Path

VERSAO_ELEMENTOS = "1.9.2"
COMMIT_PLACAS = "962b19d5636756537a93bb5337ac99abd775eae0"


def chave_conexao(c):
    """Identifica uma ligação sem depender da ordem das pontas."""
    return " | ".join(sorted([c[0], c[1]]))


def ligacoes(diagrama):
    """Ligações entre peças (sem o monitor serial), como pares (de, para, cor)."""
    return [
        (c[0], c[1], c[2] if len(c) > 2 else "")
        for c in diagrama.get("connections", [])
        if not c[0].startswith("$") and not c[1].startswith("$")
    ]


def novidades(diagrama, anterior):
    """Peças e ligações que não existiam na versão anterior do diagrama."""
    if not anterior:
        return set()
    pecas = {p["id"] for p in anterior.get("parts", [])}
    conexoes = {chave_conexao(c) for c in anterior.get("connections", [])}
    novas = {p["id"] for p in diagrama.get("parts", []) if p["id"] not in pecas}
    novas |= {chave_conexao(c) for c in diagrama.get("connections", []) if chave_conexao(c) not in conexoes}
    return novas


def telas_atualizadas(pasta):
    """{id da peça: PNG em base64} das capturas mais novas que o diagrama e o código."""
    pasta = Path(pasta)
    referencia = max((f.stat().st_mtime for f in [pasta / "diagram.json", *pasta.glob("*.ino")] if f.exists()), default=0)
    return {
        png.stem: base64.b64encode(png.read_bytes()).decode()
        for png in sorted((pasta / "telas").glob("*.png"))
        if png.stat().st_mtime >= referencia
    }
