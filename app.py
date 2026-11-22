"""Interface Streamlit do Assistente de Bancada: chat à esquerda, bancada à direita.

Uso: streamlit run app.py
"""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver

RAIZ = Path(__file__).resolve().parent
load_dotenv(RAIZ / ".env")

from agente.grafo import criar_modelo, responder  # noqa: E402
from agente.guardrails import remover_segredos  # noqa: E402
from painel_bancada import html_bancada, ligacoes, novidades, telas_atualizadas  # noqa: E402

PASTA_PROJETOS = Path(os.environ.get("PASTA_PROJETOS", RAIZ / "projetos"))

st.set_page_config(page_title="Assistente de Bancada", page_icon=":material/memory:", layout="wide")


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
    st.session_state.projeto = None  # projeto mostrado na bancada
    st.session_state.diagramas = {}  # última versão exibida de cada projeto (para destacar o que mudou)
    st.session_state.destaques = set()
    st.session_state.serial = ""


if "thread_id" not in st.session_state:
    nova_conversa()


def ler_diagrama(projeto):
    caminho = PASTA_PROJETOS / projeto / "diagram.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def serial_sem_boot(texto):
    """Tira o cabeçalho de boot do ESP32 (até a linha 'entry 0x...') e o aviso da ferramenta."""
    partes = re.split(r"^entry 0x[0-9a-f]+\s*$", texto, flags=re.M)
    return partes[-1].strip()


def atualizar_bancada(b):
    """Acompanha o projeto em que o agente está mexendo, pelas ferramentas chamadas."""
    anterior = None
    for f in b["ferramentas"]:
        if f["nome"] == "salvar_projeto" and '"pasta"' in f["resultado"]:
            st.session_state.projeto = f["argumentos"].get("nome")
            anterior = anterior or st.session_state.diagramas.get(st.session_state.projeto)
        elif f["nome"] in ("compilar", "capturar_display", "ler_projeto") and not f["erro"]:
            st.session_state.projeto = f["argumentos"].get("projeto") or f["argumentos"].get("nome")
        elif f["nome"] in ("esperar_serial", "wokwi_read_serial") and f["resultado"]:
            st.session_state.serial = serial_sem_boot(f["resultado"])
    projeto = st.session_state.projeto
    diagrama = ler_diagrama(projeto) if projeto else None
    if diagrama:
        st.session_state.destaques = novidades(diagrama, anterior) if anterior else set()
        st.session_state.diagramas[projeto] = diagrama


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


def mostrar_bancada():
    projetos = sorted(p.parent.name for p in PASTA_PROJETOS.glob("*/diagram.json"))
    atual = st.session_state.projeto
    escolhido = st.selectbox(
        "Projeto na bancada", projetos, index=projetos.index(atual) if atual in projetos else None,
        placeholder="Nenhum projeto ainda", label_visibility="collapsed",
    )
    if escolhido != atual:
        st.session_state.projeto, st.session_state.destaques, st.session_state.serial = escolhido, set(), ""
        atual = escolhido
    diagrama = ler_diagrama(atual) if atual else None
    if diagrama:
        # versão que o usuário está vendo: base para destacar o que a próxima resposta mudar
        st.session_state.diagramas.setdefault(atual, diagrama)
    if not diagrama:
        st.caption("O circuito aparece aqui quando o assistente salvar um projeto. "
                   "Você também pode abrir um projeto salvo e pedir mudanças no chat.")
        return

    aba_circuito, aba_ligacoes, aba_codigo, aba_serial = st.tabs(["Circuito", "Ligações", "Código", "Serial"])
    with aba_circuito:
        components.html(html_bancada(diagrama, telas_atualizadas(PASTA_PROJETOS / atual), st.session_state.destaques),
                        height=470)
        if st.session_state.destaques:
            st.caption("Em destaque (tracejado ou contorno laranja): o que mudou na última resposta.")
    with aba_ligacoes:
        linhas = [{"De": de, "Para": para, "Cor": cor,
                   "Nova": "sim" if " | ".join(sorted([de, para])) in st.session_state.destaques else ""}
                  for de, para, cor in ligacoes(diagrama)]
        st.dataframe(linhas, hide_index=True, use_container_width=True)
    with aba_codigo:
        sketch = PASTA_PROJETOS / atual / f"{atual}.ino"
        st.code(sketch.read_text(encoding="utf-8") if sketch.exists() else "", language="cpp")
    with aba_serial:
        if st.session_state.serial:
            st.code(st.session_state.serial, language=None)
        else:
            st.caption("A saída da serial aparece aqui depois de uma simulação.")


with st.sidebar:
    st.title("Assistente de Bancada")
    st.caption("Protótipos com ESP32 no Wokwi, do datasheet à placa.")
    st.button("Nova conversa", on_click=nova_conversa, type="primary", use_container_width=True)
    st.caption(f"Conversa `{st.session_state.thread_id[:8]}`")

coluna_chat, coluna_bancada = st.columns([5, 4], gap="large")

with coluna_bancada:
    st.subheader("Bancada")
    mostrar_bancada()

with coluna_chat:
    mensagens = st.container(height=640, border=False)
    with mensagens:
        for item in st.session_state.historico:
            with st.chat_message(item["papel"]):
                st.markdown(item["texto"])
                if item.get("bastidores"):
                    mostrar_bastidores(item["bastidores"])
        if not st.session_state.historico:
            st.info(
                "Descreva o circuito que você quer montar, por exemplo: "
                "\"Monte um termômetro com DHT22 e display SSD1306 no ESP32\", ou pergunte algo de um datasheet. "
                "O circuito aparece na bancada ao lado, e você pode pedir mudanças nele."
            )

    if pedido := st.chat_input("Descreva o circuito ou peça uma mudança"):
        # o agente sabe qual projeto está aberto na bancada (pode ter sido escolhido pelo usuário)
        contexto = f"[Projeto aberto na bancada: {st.session_state.projeto}]\n" if st.session_state.projeto else ""
        st.session_state.historico.append({"papel": "user", "texto": pedido})
        with mensagens:
            with st.chat_message("user"):
                st.markdown(pedido)
            with st.chat_message("assistant"):
                with st.status("Pensando...", expanded=False) as status:
                    try:
                        texto, b = asyncio.run(responder(
                            checkpointer(), st.session_state.thread_id, contexto + pedido, modelo(),
                            ao_progresso=lambda passo: status.update(label=passo[:1].upper() + passo[1:] + "..."),
                        ))
                        status.update(label="Pronto", state="complete")
                    except Exception as erro:  # ex.: token ausente, cota do modelo, wokwi-cli não instalado
                        status.update(label="Erro", state="error")
                        texto, b = remover_segredos(f"Não consegui responder: {erro}")[0], None
        st.session_state.historico.append({"papel": "assistant", "texto": texto, "bastidores": b})
        if b:
            atualizar_bancada(b)
        st.rerun()  # redesenha a bancada com o projeto atualizado
