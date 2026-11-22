"""Interface Streamlit do Assistente de Bancada.

Uso: streamlit run app.py
"""

import asyncio
import json
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv(Path(__file__).resolve().parent / ".env")

from agente.grafo import criar_modelo, responder  # noqa: E402
from agente.guardrails import remover_segredos  # noqa: E402

st.set_page_config(page_title="Assistente de Bancada", page_icon=":material/memory:")


# O Streamlit reexecuta este script a cada mensagem. O checkpointer (onde as
# conversas ficam) e o modelo são criados uma vez só. O grafo é montado a cada
# resposta, porque as ferramentas MCP valem só enquanto a sessão está aberta.
@st.cache_resource
def checkpointer():
    return InMemorySaver()


@st.cache_resource
def modelo():
    return criar_modelo()


def nova_conversa():
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.historico = []  # [{papel, texto, bastidores}] só para exibir


if "thread_id" not in st.session_state:
    nova_conversa()


def mostrar_bastidores(b):
    partes = []
    if b["skills"]:
        partes.append(f"{len(b['skills'])} skill")
    if b["ferramentas"]:
        partes.append(f"{len(b['ferramentas'])} ferramenta(s)")
    if b["trechos"]:
        partes.append(f"{len(b['trechos'])} trecho(s)")
    if b["bloqueado_por"]:
        partes.append(f"bloqueado: {b['bloqueado_por']}")
    with st.expander("Bastidores" + (f" ({', '.join(partes)})" if partes else "")):
        st.markdown("**Guardrails**")
        for g in b["guardrails"]:
            st.markdown(f"- {g}")

        if b["skills"]:
            st.markdown("**Skills carregadas**")
            for s in b["skills"]:
                st.markdown(f"- `{s}`")

        if b["ferramentas"]:
            st.markdown("**Ferramentas chamadas**")
            for i, f in enumerate(b["ferramentas"], 1):
                marca = " (erro)" if f["erro"] else ""
                st.markdown(f"{i}. `{f['nome']}`{marca}")
                st.code(json.dumps(f["argumentos"], ensure_ascii=False, indent=2)[:3000], language="json")
                if f["resultado"]:
                    st.caption("Resultado")
                    st.code(f["resultado"], language=None)

        if b["trechos"]:
            st.markdown("**Trechos recuperados**")
            for t in b["trechos"]:
                pagina = f"p. {t['pagina']}" if t["pagina"] else "página web"
                secao = f", {t['secao']}" if t.get("secao") else ""
                st.markdown(f"- [{t['titulo']}]({t['url']}), {pagina}{secao} (pontuação {t['pontuacao']})")


with st.sidebar:
    st.title("Assistente de Bancada")
    st.caption("Protótipos com ESP32 no Wokwi, do datasheet à placa.")
    st.button("Nova conversa", on_click=nova_conversa, type="primary", use_container_width=True)
    st.caption(f"Conversa `{st.session_state.thread_id[:8]}`")

for item in st.session_state.historico:
    with st.chat_message(item["papel"]):
        st.markdown(item["texto"])
        if item.get("bastidores"):
            mostrar_bastidores(item["bastidores"])

if not st.session_state.historico:
    st.info(
        "Descreva o circuito que você quer montar, por exemplo: "
        "\"Monte um termômetro com DHT22 e display SSD1306 no ESP32\", ou pergunte algo de um datasheet."
    )

if pedido := st.chat_input("Descreva o circuito ou faça uma pergunta"):
    st.session_state.historico.append({"papel": "user", "texto": pedido})
    with st.chat_message("user"):
        st.markdown(pedido)

    with st.chat_message("assistant"):
        with st.status("Pensando...", expanded=False) as status:
            try:
                texto, b = asyncio.run(responder(
                    checkpointer(), st.session_state.thread_id, pedido, modelo(),
                    ao_progresso=lambda passo: status.update(label=passo[:1].upper() + passo[1:] + "..."),
                ))
                status.update(label="Pronto", state="complete")
            except Exception as erro:  # ex.: token ausente, cota do modelo, wokwi-cli não instalado
                status.update(label="Erro", state="error")
                texto, b = remover_segredos(f"Não consegui responder: {erro}")[0], None
        st.markdown(texto)
        if b:
            mostrar_bastidores(b)
    st.session_state.historico.append({"papel": "assistant", "texto": texto, "bastidores": b})
