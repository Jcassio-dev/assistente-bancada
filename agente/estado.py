"""Estado do grafo."""

from langgraph.graph import MessagesState


class Estado(MessagesState):
    # Guardrail que barrou o pedido ("injection", "fora_do_escopo") ou None.
    bloqueado_por: str | None
    # Pedido envolve rede elétrica: a resposta leva aviso de segurança.
    alerta_seguranca: bool
    # Trechos do RAG recuperados nesta resposta (artifact do buscar_documentos):
    # fonte aceita pelo guardrail de saída e exibida nos bastidores da interface.
    trechos_recuperados: list[dict]
    # O que os guardrails fizeram nesta resposta (ex.: "entrada: classificador: ok",
    # "saída: aviso de rede elétrica"), para os bastidores da interface.
    guardrails: list[str]
