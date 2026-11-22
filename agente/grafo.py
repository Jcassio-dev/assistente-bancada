"""Grafo do agente: guardrails, agente, ferramentas e memória por conversa.

START -> guardrail_entrada -(bloqueado)-> recusa -> END
                           -(ok)-> agente <-> ferramentas
                                   agente -(sem tool_calls)-> guardrail_saida -> END

As ferramentas MCP só valem enquanto a sessão MCP está aberta (agente/mcp_config.py),
então o grafo é montado a cada resposta com as ferramentas da sessão. O checkpointer
é criado uma vez e passado para todos os grafos: é ele que guarda as conversas.
"""

import os

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agente.estado import Estado
from agente.guardrails import avaliar_entrada, revisar_saida

LIMITE_PASSOS = 60  # recursion_limit: cada ida e volta agente/ferramentas gasta 2


def criar_modelo():
    nome = os.environ.get("MODELO")
    if not nome:
        raise RuntimeError("Defina MODELO no .env, no formato provedor:nome (veja o .env.example).")
    return init_chat_model(nome, temperature=0)


def ferramentas_locais():
    """Ferramentas que rodam neste processo (as outras vêm dos servidores MCP)."""
    from agente.rag import buscar_documentos
    from agente.skills import carregar_skill

    return [buscar_documentos, carregar_skill]


RESPOSTAS_RECUSA = {
    "injection": (
        "Não posso seguir esse pedido: ele tenta mudar as minhas instruções ou obter "
        "informações internas, como chaves e configurações."
    ),
    "fora_do_escopo": "Esse pedido está fora do que eu faço.",
}
APRESENTACAO = (
    " Eu ajudo a prototipar circuitos com ESP32 no simulador Wokwi (consultando os datasheets, "
    "montando, validando, compilando e simulando) e a preparar o circuito para uma placa de "
    "circuito impresso. Se quiser, descreva o circuito que você quer montar."
)


def fontes_da_conversa(estado, mensagem):
    """Texto aceito como fonte de valores técnicos pelo guardrail de saída.

    Mensagem de sistema, pedidos do usuário, argumentos e resultados das
    ferramentas e trechos do RAG. O texto das respostas do próprio modelo não conta.
    """
    partes = [mensagem]
    for m in estado["messages"]:
        if isinstance(m, (HumanMessage, ToolMessage)):
            partes.append(m.text)
        for chamada in getattr(m, "tool_calls", None) or []:
            partes.append(str(chamada["args"]))
    partes += [t.get("texto", "") for t in estado.get("trechos_recuperados") or []]
    return "\n".join(partes)


def montar_grafo(ferramentas, checkpointer=None, modelo=None, mensagem=None, classificador=None):
    """Compila o grafo.

    ferramentas: lista completa (ferramentas_locais() + as da sessão MCP).
    modelo, mensagem e classificador: para os testes; por padrão, MODELO do .env,
    mensagem_sistema() e o próprio modelo (sem ferramentas) classificando a entrada.
    """
    if mensagem is None:
        from agente.prompts import mensagem_sistema

        mensagem = mensagem_sistema()
    modelo = modelo or criar_modelo()
    classificador = classificador or modelo
    modelo_com_ferramentas = modelo.bind_tools(ferramentas)
    executor = ToolNode(ferramentas)

    async def guardrail_entrada(estado: Estado):
        # Também zera os campos de controle, que valem só para esta pergunta.
        avaliacao = await avaliar_entrada(classificador, estado["messages"][-1].text)
        return {
            "bloqueado_por": avaliacao["bloqueado_por"],
            "alerta_seguranca": avaliacao["alerta_seguranca"],
            "trechos_recuperados": [],
            "guardrails": [f"entrada: {avaliacao['motivo']}"],
        }

    def depois_da_entrada(estado: Estado):
        return "recusa" if estado.get("bloqueado_por") else "agente"

    async def recusa(estado: Estado):
        motivo = RESPOSTAS_RECUSA.get(estado["bloqueado_por"], RESPOSTAS_RECUSA["fora_do_escopo"])
        return {"messages": [AIMessage(motivo + APRESENTACAO)]}

    async def agente(estado: Estado):
        resposta = await modelo_com_ferramentas.ainvoke([SystemMessage(mensagem), *estado["messages"]])
        return {"messages": [resposta]}

    def depois_do_agente(estado: Estado):
        return "ferramentas" if estado["messages"][-1].tool_calls else "guardrail_saida"

    async def ferramentas_no(estado: Estado):
        resultado = await executor.ainvoke(estado)
        novos = [
            t
            for m in resultado["messages"]
            if m.name == "buscar_documentos" and isinstance(m.artifact, list)
            for t in m.artifact
        ]
        saida = {"messages": resultado["messages"]}
        if novos:
            saida["trechos_recuperados"] = (estado.get("trechos_recuperados") or []) + novos
        return saida

    async def guardrail_saida(estado: Estado):
        final = estado["messages"][-1]
        texto, acoes = revisar_saida(final.text, fontes_da_conversa(estado, mensagem), estado.get("alerta_seguranca"))
        if not acoes:
            return {}
        # mesmo id: o add_messages substitui a resposta em vez de acrescentar outra
        return {
            "messages": [AIMessage(texto, id=final.id)],
            "guardrails": (estado.get("guardrails") or []) + [f"saída: {a}" for a in acoes],
        }

    grafo = StateGraph(Estado)
    grafo.add_node("guardrail_entrada", guardrail_entrada)
    grafo.add_node("recusa", recusa)
    grafo.add_node("agente", agente)
    grafo.add_node("ferramentas", ferramentas_no)
    grafo.add_node("guardrail_saida", guardrail_saida)

    grafo.add_edge(START, "guardrail_entrada")
    grafo.add_conditional_edges("guardrail_entrada", depois_da_entrada, ["recusa", "agente"])
    grafo.add_edge("recusa", END)
    grafo.add_conditional_edges("agente", depois_do_agente, ["ferramentas", "guardrail_saida"])
    grafo.add_edge("ferramentas", "agente")
    grafo.add_edge("guardrail_saida", END)
    return grafo.compile(checkpointer=checkpointer)


def configuracao(thread_id):
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": LIMITE_PASSOS}
