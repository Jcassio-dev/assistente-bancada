from langgraph.graph import MessagesState


class Estado(MessagesState):
    bloqueado_por: str | None  # "injection", "fora_do_escopo" ou None
    alerta_seguranca: bool  # rede elétrica: a resposta leva aviso
    trechos_recuperados: list[dict]  # fonte aceita pelo guardrail de saída
    guardrails: list[str]  # o que os guardrails fizeram, para os bastidores
    revisao_pedida: bool  # a saída só devolve ao agente uma vez por pergunta
