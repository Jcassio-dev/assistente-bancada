"""Interface Streamlit do Assistente de Bancada.

Cada conversa é uma bancada: o chat fica à esquerda e o circuito do projeto da
conversa à direita, redesenhado enquanto o agente monta.

Uso: streamlit run app.py
"""

import asyncio
import json
from collections import Counter
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

RAIZ = Path(__file__).resolve().parent
load_dotenv(RAIZ / ".env")

from agente.grafo import criar_modelo, responder  # noqa: E402
from agente.guardrails import remover_segredos  # noqa: E402
from interface import conversas  # noqa: E402
from interface.acompanhamento import (  # noqa: E402
    PASTA_PROJETOS,
    etapas_visiveis,
    ler_diagrama,
    mover_peca,
    registrar,
    rotulo,
    serial_sem_boot,
)
from interface.exportar import NOVO_PROJETO_ESP32, pacote_wokwi  # noqa: E402
from interface.mesa import mesa  # noqa: E402
from interface.painel import ligacoes, telas_atualizadas  # noqa: E402
from interface.simulacao import SimulacaoAoVivo, controles_do_diagrama, leds_do_diagrama  # noqa: E402
from servidor_bancada.servidor import compilar, gerar_bom  # noqa: E402

st.set_page_config(page_title="Assistente de Bancada", page_icon=":material/memory:", layout="wide")

SUGESTOES = [
    ("Termômetro com display", "DHT22 e OLED SSD1306",
     "Monte um termômetro com ESP32, um sensor DHT22 e um display OLED SSD1306 mostrando temperatura e umidade. Simule."),
    ("Alerta de distância", "HC-SR04 e LED",
     "Monte um medidor de distância com HC-SR04 que acende um LED vermelho quando algo chegar a menos de 20 cm. Simule."),
    ("Primeiro circuito", "LED piscando no GPIO2",
     "Monte um LED piscando no GPIO2 a cada meio segundo, escrevendo o estado na serial. Simule."),
    ("Pergunta de datasheet", "corrente máxima de um GPIO",
     "Qual a corrente máxima que um GPIO do ESP32 consegue fornecer?"),
]

ESTILO = """
<style>
  .block-container { padding-top: 2.2rem; padding-bottom: 1rem; max-width: 100%; }
  .st-key-lista-bancadas .stButton button { justify-content: flex-start; padding: .35rem .7rem; }
  .st-key-lista-bancadas .stButton button > div { justify-content: flex-start; width: 100%; }
  .st-key-lista-bancadas .stButton button p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
  .st-key-lista-bancadas [data-testid="stBaseButton-tertiary"] { color: #b9c2bd; }
  .st-key-lista-bancadas [data-testid="stBaseButton-secondary"] { background: #252d30; border-color: #3a4447; }
  [data-testid="stSidebar"] hr { margin: .8rem 0 .4rem 0; }
  .titulo-bancada { display: flex; align-items: baseline; gap: .6rem; margin: 0 0 .35rem 0; }
  .titulo-bancada b { font-size: 1.35rem; font-weight: 700; color: #e4e7e5; }
  .titulo-bancada span { color: #8a958f; font-size: .85rem; font-family: ui-monospace, monospace; }
  .etapas { margin: 0 0 .7rem 0; min-height: 1.6rem; }
  .pilula { display: inline-block; padding: .1rem .6rem; margin: 0 .35rem .3rem 0; border-radius: 999px;
            font-size: .78rem; border: 1px solid; }
  .pilula.ok { color: #86d9a6; background: #183326; border-color: #2c5a41; }
  .pilula.erro { color: #f2a097; background: #3a1d1a; border-color: #6b302a; }
  .pilula.neutra { color: #b9c2bd; background: #22282a; border-color: #394145; }
  .boas-vindas { padding: 2.5rem 0 1.2rem 0; }
  .boas-vindas h1 { font-size: 2rem; margin-bottom: .3rem; }
  .boas-vindas p { color: #9aa5a0; font-size: 1.02rem; max-width: 40rem; }
  [data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2 { font-size: 1.15rem; padding: .6rem 0 .2rem 0; }
  [data-testid="stChatMessage"] h3, [data-testid="stChatMessage"] h4 { font-size: 1.02rem; padding: .5rem 0 .1rem 0; }
  .st-key-sugestoes .stButton button { min-height: 4.6rem; justify-content: flex-start; padding: .7rem 1rem; }
  .st-key-sugestoes .stButton button div, .st-key-sugestoes .stButton button p { text-align: left; width: 100%; }
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)


@st.cache_resource
def modelo():
    return criar_modelo()


async def rodar_agente(thread_id, pedido, ao_progresso):
    # Uma conexão por resposta: o asyncio.run cria um laço novo a cada mensagem.
    conversas.PASTA.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(conversas.MEMORIA)) as checkpointer:
        return await responder(checkpointer, thread_id, pedido, modelo(), ao_progresso)


async def apagar_memoria(thread_id):
    async with AsyncSqliteSaver.from_conn_string(str(conversas.MEMORIA)) as checkpointer:
        await checkpointer.adelete_thread(thread_id)


# ---------- conversa ativa (fica na URL: ?c=<id>) ----------

def conversa_ativa():
    id_ = st.query_params.get("c")
    if "conversa" in st.session_state and st.session_state.conversa["id"] == id_:
        return st.session_state.conversa
    conversa = conversas.carregar(id_) if id_ else None
    if conversa is None and "conversa" in st.session_state and not id_ \
            and not st.session_state.conversa["historico"]:
        return st.session_state.conversa  # bancada nova ainda sem mensagem: mantém a mesma
    st.session_state.conversa = conversa or conversas.nova()
    return st.session_state.conversa


def abrir(id_=None):
    if id_:
        st.query_params["c"] = id_
    else:
        st.query_params.clear()
    st.session_state.pop("conversa", None)


def abrir_projeto(projeto):
    existente = next((c for c in conversas.listar() if c["projeto"] == projeto), None)
    if existente:  # o projeto já tem bancada: volta para ela em vez de criar outra
        abrir(existente["id"])
        return
    conversa = conversas.nova(projeto)
    conversa["diagrama"] = ler_diagrama(projeto)
    conversas.salvar(conversa)
    abrir(conversa["id"])


conversa = conversa_ativa()


# ---------- barra lateral ----------

with st.sidebar:
    st.markdown("### Assistente de Bancada")
    st.caption("Protótipos com ESP32: do datasheet à simulação e à placa.")
    st.button("Nova bancada", icon=":material/add:", type="primary", use_container_width=True, on_click=abrir)

    salvas = conversas.listar()
    with st.container(key="lista-bancadas"):
        if salvas:
            st.caption("Suas bancadas")
        repetidos = Counter(c["titulo"] for c in salvas)
        for c in salvas:
            ativa = c["id"] == conversa["id"]
            titulo = c["titulo"] or "Sem título"
            if repetidos[c["titulo"]] > 1:  # duas bancadas do mesmo projeto: diferencia pela data
                titulo += f" ({conversas.quando(c['atualizada'])})"
            st.button(titulo, key=f"conv-{c['id']}", use_container_width=True,
                      type="secondary" if ativa else "tertiary",
                      icon=":material/developer_board:" if c["projeto"] else ":material/chat_bubble:",
                      on_click=abrir, args=(c["id"],))

    st.divider()
    projetos = sorted(p.parent.name for p in PASTA_PROJETOS.glob("*/diagram.json"))
    if projetos:
        with st.popover("Abrir projeto salvo", icon=":material/folder_open:", type="tertiary"):
            st.caption("Abre o projeto numa bancada nova, para continuar de onde parou.")
            for p in projetos:
                st.button(p, key=f"proj-{p}", type="tertiary", on_click=abrir_projeto, args=(p,))

    if conversa["historico"] or conversa["projeto"]:
        with st.popover("Apagar esta bancada", icon=":material/delete:", type="tertiary"):
            st.caption("Apaga a conversa e a memória dela. Os arquivos do projeto continuam em projetos/.")
            if st.button("Apagar", type="primary"):
                asyncio.run(apagar_memoria(conversa["id"]))
                conversas.apagar(conversa["id"])
                abrir()
                st.rerun()


# ---------- bancada ----------

def pilulas(conversa):
    itens = etapas_visiveis(conversa.get("etapas"))
    if not itens:
        texto = "Projeto salvo" if conversa.get("projeto") else "Nenhum circuito ainda"
        itens = [(texto, "neutra")]
    return "".join(f'<span class="pilula {situacao}">{texto}</span>' for texto, situacao in itens)


# ---------- simulação ao vivo ----------

@st.cache_resource
def simulacoes():
    """id da conversa -> SimulacaoAoVivo. Vale entre as reexecuções do script."""
    return {}


def parar_simulacao(id_):
    sim = simulacoes().pop(id_, None)
    if sim:
        sim.parar()


def precisa_compilar(projeto):
    pasta = PASTA_PROJETOS / projeto
    firmware = next((pasta / "build").glob("*.merged.bin"), None) if (pasta / "build").exists() else None
    sketches = [f.stat().st_mtime for f in pasta.glob("*.ino")]
    return firmware is None or (sketches and firmware.stat().st_mtime < max(sketches))


def ligar_simulacao(conversa, diagrama):
    projeto = conversa["projeto"]
    if precisa_compilar(projeto):
        with st.spinner("Compilando o firmware antes de simular..."):
            r = compilar(projeto)
        if not r.get("sucesso"):
            erros = "; ".join(f"linha {e['linha']}: {e['mensagem']}" for e in r.get("erros", [])[:3])
            st.session_state.aviso_simulacao = "O projeto não compilou. " + (erros or r.get("erro", ""))
            return
    simulacoes()[conversa["id"]] = SimulacaoAoVivo(projeto, PASTA_PROJETOS / projeto, leds_do_diagrama(diagrama))


def tratar_eventos(conversa, resultado):
    """Peça arrastada/girada na mesa e controles da simulação ao vivo."""
    if movida := getattr(resultado, "mover", None):
        # uma peça arrastada, ou várias afastadas sozinhas ao montar ({"pecas": [...]})
        for m in movida.get("pecas") or [movida]:
            mover_peca(conversa["projeto"], m["id"], m["left"], m["top"], m.get("rotate", 0))
    sim = simulacoes().get(conversa["id"])
    if sim and (controle := getattr(resultado, "controle", None)):
        sim.controlar(controle["parte"], controle["controle"], controle["valor"])
    if sim and (botao := getattr(resultado, "botao", None)):
        sim.apertar(botao["parte"])


@st.fragment(run_every=0.7)
def mesa_ao_vivo(conversa, diagrama, telas):
    """Mesa com a simulação ligada: a cada segundo atualiza LEDs, serial e tempo, sem redesenhar."""
    id_ = conversa["id"]
    sim = simulacoes().get(id_)
    if sim is None:
        st.rerun()
    estado = sim.estado()
    if not estado["ativa"] and not estado["iniciando"]:
        simulacoes().pop(id_, None)
        st.session_state.aviso_simulacao = estado["erro"] or "Simulação desligada."
        st.rerun()
    linhas = [l for l in serial_sem_boot(estado["serial"]).splitlines() if l.strip()]
    ao_vivo = {"iniciando": estado["iniciando"], "acesos": estado["acesos"],
               "serial": "\n".join(linhas[-80:]), "restante": estado["restante"]}
    resultado = mesa(f"mesa-vivo-{id_}", diagrama, telas, None, ao_vivo, controles_do_diagrama(diagrama), altura=420)
    tratar_eventos(conversa, resultado)


def barra_da_bancada(conversa, diagrama):
    projeto = conversa["projeto"]
    ao_vivo = conversa["id"] in simulacoes()
    c1, c2 = st.columns(2)
    if ao_vivo:
        c1.button("Parar simulação", icon=":material/stop:", use_container_width=True,
                  on_click=parar_simulacao, args=(conversa["id"],))
    elif c1.button("Simular ao vivo", icon=":material/play_arrow:", type="primary", use_container_width=True):
        ligar_simulacao(conversa, diagrama)
        st.rerun()
    with c2.popover("Levar para o Wokwi", icon=":material/open_in_new:", use_container_width=True):
        nome, dados = pacote_wokwi(PASTA_PROJETOS / projeto)
        st.markdown(
            "O Wokwi não abre projetos de fora por link, então são três passos:\n"
            "1. Baixe os arquivos.\n"
            "2. Abra um projeto ESP32 novo no Wokwi.\n"
            "3. Cole `sketch.ino` e `diagram.json` nas abas de mesmo nome e crie o `libraries.txt` "
            "(menu de arquivos, *New file*) com o conteúdo do arquivo baixado."
        )
        st.download_button("Baixar arquivos (.zip)", dados, nome, "application/zip", icon=":material/download:",
                           use_container_width=True)
        st.link_button("Abrir projeto ESP32 no Wokwi", NOVO_PROJETO_ESP32, icon=":material/open_in_new:",
                       use_container_width=True)
        st.caption(f"No VS Code com a extensão do Wokwi, a pasta `projetos/{projeto}` já abre direto "
                   "(Wokwi: Start Simulator).")


def desenhar_bancada(alvo, conversa, durante_resposta=False):
    projeto = conversa.get("projeto")
    diagrama = ler_diagrama(projeto) if projeto else None
    ao_vivo = conversa["id"] in simulacoes() and not durante_resposta
    with alvo.container():
        nome = f"<span>projetos/{projeto}</span>" if projeto else ""
        extra = '<span class="pilula ok">Simulação ao vivo</span>' if ao_vivo else ""
        st.markdown(f'<div class="titulo-bancada"><b>Bancada</b>{nome}</div>'
                    f'<div class="etapas">{pilulas(conversa)}{extra}</div>', unsafe_allow_html=True)
        if aviso := st.session_state.pop("aviso_simulacao", None):
            st.toast(aviso, icon=":material/info:")
        if diagrama and not durante_resposta:
            barra_da_bancada(conversa, diagrama)
        telas = telas_atualizadas(PASTA_PROJETOS / projeto) if diagrama else {}
        aba_circuito, aba_ligacoes, aba_materiais, aba_codigo, aba_serial = st.tabs(
            ["Circuito", "Ligações", "Materiais", "Código", "Serial"])
        with aba_circuito:
            if ao_vivo:
                mesa_ao_vivo(conversa, diagrama, telas)
            else:
                # durante a resposta a mesa é redesenhada várias vezes na mesma execução: chave nova a cada vez
                if durante_resposta:
                    st.session_state.desenhos = st.session_state.get("desenhos", 0) + 1
                chave = f"mesa-{conversa['id']}" + (f"-{st.session_state.desenhos}" if durante_resposta else "")
                resultado = mesa(chave, diagrama, telas, conversa.get("destaques"), editavel=not durante_resposta)
                if not durante_resposta:
                    tratar_eventos(conversa, resultado)
                if conversa.get("destaques") and diagrama:
                    st.caption("Contorno laranja: o que mudou na última resposta.")
        if not diagrama:
            for aba in (aba_ligacoes, aba_materiais, aba_codigo, aba_serial):
                aba.caption("Aparece quando houver um circuito na bancada.")
            return
        with aba_ligacoes:
            destaques = set(conversa.get("destaques") or [])
            st.dataframe([{"De": de, "Para": para, "Cor": cor,
                           "Nova": "sim" if " | ".join(sorted([de, para])) in destaques else ""}
                          for de, para, cor in ligacoes(diagrama)], hide_index=True, use_container_width=True)
        with aba_materiais:
            bom = gerar_bom(json.dumps(diagrama))
            st.dataframe([{"Qtd.": i["quantidade"], "Peça": i["descricao"], "Referências": ", ".join(i["referencias"])}
                          for i in bom.get("itens", [])], hide_index=True, use_container_width=True)
        with aba_codigo:
            sketch = PASTA_PROJETOS / projeto / f"{projeto}.ino"
            st.code(sketch.read_text(encoding="utf-8") if sketch.exists() else "", language="cpp", height=440)
        with aba_serial:
            if conversa.get("serial"):
                st.code(conversa["serial"], language=None, height=440)
            else:
                st.caption("A saída da serial aparece aqui depois de uma simulação.")


# ---------- chat ----------

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
    with st.expander("Bastidores" + (f" ({', '.join(partes)})" if partes else ""), icon=":material/build:"):
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


def boas_vindas():
    st.markdown(
        '<div class="boas-vindas"><h1>O que vamos montar?</h1>'
        "<p>Descreva o circuito. O assistente consulta os datasheets, monta na bancada ao lado, "
        "confere as ligações, compila e simula no Wokwi. Depois é só pedir mudanças.</p></div>",
        unsafe_allow_html=True,
    )
    with st.container(key="sugestoes"):
        colunas = st.columns(2)
        for i, (titulo, detalhe, pedido) in enumerate(SUGESTOES):
            if colunas[i % 2].button(f"**{titulo}**  \n{detalhe}", key=f"sug-{i}", use_container_width=True):
                st.session_state.pendente = pedido
                st.rerun()


def abrir_conversa_vazia(conversa):
    if conversa["projeto"]:
        st.markdown(f'<div class="boas-vindas"><h1>{conversa["projeto"]}</h1>'
                    "<p>Projeto aberto na bancada. Peça uma mudança, uma simulação ou a preparação "
                    "para a placa.</p></div>", unsafe_allow_html=True)
    else:
        boas_vindas()


def responder_pedido(conversa, pedido, area_mensagens, painel, abertura):
    if not conversa["historico"] and not conversa["projeto"]:
        conversa["titulo"] = conversas.titulo_do_pedido(pedido)
    conversa["historico"].append({"papel": "user", "texto": pedido})
    conversas.salvar(conversa)
    if st.query_params.get("c") != conversa["id"]:
        st.query_params["c"] = conversa["id"]

    # o agente sabe qual projeto é desta conversa (pode ter vindo de "Abrir projeto salvo")
    contexto = f"[Projeto aberto na bancada: {conversa['projeto']}]\n" if conversa["projeto"] else ""
    chamadas = {}

    abertura.empty()  # tira as boas-vindas assim que o pedido sai
    # o agente pode mudar o projeto e simular por conta própria: desliga a simulação ao vivo
    parar_simulacao(conversa["id"])
    with area_mensagens:
        with st.chat_message("user"):
            st.markdown(pedido)
        with st.chat_message("assistant"):
            status = st.status("Entendendo o pedido...", expanded=True)

            def ao_progresso(no, mensagens):
                for m in mensagens:
                    if isinstance(m, AIMessage):
                        for c in m.tool_calls or []:
                            chamadas[c["id"]] = c
                            status.write(rotulo(c["name"], c["args"]))
                            status.update(label=rotulo(c["name"], c["args"]) + "...", expanded=True)
                    elif isinstance(m, ToolMessage):
                        c = chamadas.get(m.tool_call_id, {})
                        if registrar(conversa, m.name, c.get("args"), m.text, m.status == "error"):
                            desenhar_bancada(painel, conversa, durante_resposta=True)
                    elif isinstance(m, HumanMessage) and m.additional_kwargs.get("verificacao"):
                        status.write("Conferindo a resposta: um passo não foi confirmado, refazendo")
                if no == "agente" and not any(getattr(m, "tool_calls", None) for m in mensagens):
                    status.update(label="Escrevendo a resposta...", expanded=True)

            try:
                texto, b = asyncio.run(rodar_agente(conversa["id"], contexto + pedido, ao_progresso))
                status.update(label="Pronto", state="complete", expanded=False)
            except Exception as erro:  # ex.: token ausente, cota do modelo, wokwi-cli não instalado
                status.update(label="Erro", state="error", expanded=True)
                texto, b = remover_segredos(f"Não consegui responder: {erro}")[0], None

    conversa["historico"].append({"papel": "assistant", "texto": texto, "bastidores": b})
    conversas.salvar(conversa)
    st.rerun()


coluna_chat, coluna_bancada = st.columns([11, 10], gap="large")

with coluna_bancada:
    painel = st.empty()
    desenhar_bancada(painel, conversa)

with coluna_chat:
    area_mensagens = st.container(height=640, border=False)
    with area_mensagens:
        abertura = st.empty()
        if not conversa["historico"]:
            with abertura.container():
                abrir_conversa_vazia(conversa)
        for item in conversa["historico"]:
            with st.chat_message(item["papel"]):
                st.markdown(item["texto"])
                if item.get("bastidores"):
                    mostrar_bastidores(item["bastidores"])
        if conversa["historico"] and conversa["historico"][-1]["papel"] == "user":
            # a página foi fechada ou recarregada no meio da resposta
            st.caption("A resposta a este pedido foi interrompida antes de terminar.")
            if st.button("Enviar de novo", icon=":material/refresh:", type="tertiary"):
                st.session_state.pendente = conversa["historico"].pop()["texto"]
                st.rerun()

    digitado = st.chat_input("Descreva o circuito ou peça uma mudança")
    pedido = digitado or st.session_state.pop("pendente", None)
    if pedido:
        responder_pedido(conversa, pedido, area_mensagens, painel, abertura)
