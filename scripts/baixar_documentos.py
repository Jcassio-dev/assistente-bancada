"""Baixa os documentos listados em fontes.yaml para dados/pdfs/.

Uso: python scripts/baixar_documentos.py [--forcar]
Arquivos já baixados são pulados, a menos que se passe --forcar.
"""

import sys
from pathlib import Path

import httpx
import yaml

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "pdfs"
# Alguns sites (Espressif, JLCPCB) recusam clientes sem User-Agent de navegador.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def carregar_fontes():
    return yaml.safe_load((RAIZ / "fontes.yaml").read_text(encoding="utf-8"))["documentos"]


def caminho_local(doc):
    return PASTA / f"{doc['id']}.{doc['tipo']}"


def main():
    forcar = "--forcar" in sys.argv
    PASTA.mkdir(parents=True, exist_ok=True)
    falhas = 0
    with httpx.Client(headers=CABECALHOS, follow_redirects=True, timeout=120) as cliente:
        for doc in carregar_fontes():
            destino = caminho_local(doc)
            if destino.exists() and not forcar:
                print(f"[pulado]  {doc['id']} (já existe)")
                continue
            try:
                resposta = cliente.get(doc["url"])
                resposta.raise_for_status()
            except httpx.HTTPError as e:
                print(f"[falhou]  {doc['id']}: {e}")
                falhas += 1
                continue
            # Confere se veio o que era esperado (um site pode devolver uma página de erro com status 200).
            tipo_recebido = resposta.headers.get("content-type", "")
            esperado = "application/pdf" if doc["tipo"] == "pdf" else "text/html"
            if esperado not in tipo_recebido:
                print(f"[falhou]  {doc['id']}: esperava {esperado}, recebeu {tipo_recebido}")
                falhas += 1
                continue
            destino.write_bytes(resposta.content)
            print(f"[baixado] {doc['id']} ({len(resposta.content) / 1e6:.1f} MB)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
