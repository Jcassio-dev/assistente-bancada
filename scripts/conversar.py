"""Chat pelo terminal, para testar o grafo sem a interface.

Uso: python scripts/conversar.py
Comandos: /nova (nova conversa), /sair.
"""

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.grafo import configuracao, ferramentas_locais, montar_grafo  # noqa: E402
from agente.mcp_config import ferramentas_mcp  # noqa: E402


def mostrar_bastidores(mensagens):
    """Ferramentas chamadas na resposta (com os argumentos resumidos)."""
    for m in mensagens:
        for chamada in getattr(m, "tool_calls", None) or []:
            argumentos = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in chamada["args"].items())
            print(f"   [ferramenta] {chamada['name']}({argumentos})")


async def responder(checkpointer, thread_id, texto):
    async with ferramentas_mcp() as mcp:
        grafo = montar_grafo(ferramentas_locais() + mcp, checkpointer)
        config = configuracao(thread_id)
        antes = len((await grafo.aget_state(config)).values.get("messages", []))
        estado = await grafo.ainvoke({"messages": [HumanMessage(texto)]}, config)
    novas = estado["messages"][antes:]
    mostrar_bastidores(novas)
    for t in estado.get("trechos_recuperados") or []:
        pagina = f"p. {t['pagina']}" if t["pagina"] else "web"
        print(f"   [trecho] {t['documento']} {pagina} ({t['pontuacao']})")
    if estado.get("bloqueado_por"):
        print(f"   [guardrail] {estado['bloqueado_por']}")
    return novas[-1].text  # junta os blocos de texto (alguns provedores devolvem lista)


async def main():
    load_dotenv(RAIZ / ".env")
    checkpointer = InMemorySaver()  # um só para todas as conversas desta sessão
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
        resposta = await responder(checkpointer, thread_id, texto)
        print(f"\nassistente> {resposta}")


if __name__ == "__main__":
    asyncio.run(main())
