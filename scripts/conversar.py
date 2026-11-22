"""Chat pelo terminal, para testar o grafo sem a interface.

Uso: python scripts/conversar.py
Comandos: /nova (nova conversa), /sair.
"""

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.grafo import criar_modelo, responder  # noqa: E402


def mostrar_bastidores(b):
    for s in b["skills"]:
        print(f"   [skill] {s}")
    for f in b["ferramentas"]:
        argumentos = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in f["argumentos"].items())
        print(f"   [ferramenta{' com erro' if f['erro'] else ''}] {f['nome']}({argumentos})")
    for t in b["trechos"]:
        pagina = f"p. {t['pagina']}" if t["pagina"] else "web"
        print(f"   [trecho] {t['documento']} {pagina} ({t['pontuacao']})")
    for g in b["guardrails"]:
        print(f"   [guardrail] {g}")


async def main():
    load_dotenv(RAIZ / ".env")
    checkpointer = InMemorySaver()  # um só para todas as conversas desta sessão
    modelo = criar_modelo()
    thread_id = str(uuid.uuid4())
    print(f"Conversa {thread_id[:8]}. Comandos: /nova, /sair.")
    while True:
        try:
            texto = input("\nvocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto == "/sair":
            break
        if texto == "/nova":
            thread_id = str(uuid.uuid4())
            print(f"Nova conversa {thread_id[:8]}.")
            continue
        resposta, b = await responder(checkpointer, thread_id, texto, modelo)
        mostrar_bastidores(b)
        print(f"\nassistente> {resposta}")


if __name__ == "__main__":
    asyncio.run(main())
