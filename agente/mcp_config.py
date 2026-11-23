"""Conexão com os servidores MCP: bancada (nosso) e wokwi (oficial do Wokwi).

As chaves vêm do .env (load_dotenv). Os dois servidores rodam via stdio como
processos filhos e herdam o ambiente deste processo.
"""

import asyncio
import os
import shutil
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

RAIZ = Path(__file__).resolve().parent.parent


def caminho_wokwi_cli():
    """WOKWI_CLI, depois o PATH, depois a pasta padrão do instalador."""
    candidato = os.environ.get("WOKWI_CLI") or shutil.which("wokwi-cli") or str(Path.home() / ".wokwi/bin/wokwi-cli")
    if not Path(candidato).exists():
        raise RuntimeError(
            "wokwi-cli não encontrado (procurado em WOKWI_CLI, no PATH e em ~/.wokwi/bin). "
            "Instale com: curl -L https://wokwi.com/ci/install.sh | sh"
        )
    return candidato


def pasta_projetos():
    pasta = Path(os.environ.get("PASTA_PROJETOS", RAIZ / "projetos"))
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def configuracao_servidores():
    load_dotenv(RAIZ / ".env")
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        raise RuntimeError(
            "WOKWI_CLI_TOKEN não definido. Gere um token em https://wokwi.com/dashboard/ci "
            "e coloque no .env (veja o .env.example)."
        )
    ambiente = dict(os.environ)  # token, PATH, ARDUINO_CLI, PASTA_PROJETOS
    return {
        "bancada": {
            "transport": "stdio",
            "command": sys.executable,  # o Python do venv, que tem o mcp instalado
            "args": [str(RAIZ / "servidor_bancada" / "servidor.py")],
            "env": ambiente,
        },
        "wokwi": {
            "transport": "stdio",
            "command": caminho_wokwi_cli(),
            "args": ["mcp", "--quiet", str(pasta_projetos())],
            "env": ambiente,
        },
    }


def texto_ferramenta(resultado):
    """Conteúdo de uma ferramenta MCP: string ou lista de blocos de texto."""
    if not isinstance(resultado, str):
        resultado = "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in resultado)
    return corrigir_acentos(resultado)


def corrigir_acentos(texto):
    """A serial do Wokwi chega com UTF-8 lido como Latin-1 ("Â°C" no lugar de "°C")."""
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def criar_esperar_serial(ler_serial, intervalo=1.0):
    """Ferramenta que lê a serial do Wokwi até aparecer um texto.

    O wokwi_read_serial devolve só o que já chegou. Chamado em sequência pelo
    modelo, ele lia a serial antes da primeira leitura do sensor (o sketch espera
    alguns segundos), e o modelo chegou a descrever uma saída que não veio.
    """

    async def esperar_serial(texto: str, segundos: int = 20) -> str:
        """Espera o texto aparecer na serial da simulação em andamento e devolve a saída.

        Use depois do wokwi_start_simulation, com um texto que o sketch escreve
        (ex.: "Temperatura"). segundos: tempo máximo de espera (até 60).
        """
        segundos = max(1, min(int(segundos), 60))
        saida = ""
        for _ in range(int(segundos / intervalo)):
            saida = texto_ferramenta(await ler_serial.ainvoke({}))
            if texto.lower() in saida.lower():
                return f"Texto \"{texto}\" encontrado na serial.\n\n{saida[-3000:]}"
            await asyncio.sleep(intervalo)
        return (f"O texto \"{texto}\" NÃO apareceu na serial em {segundos} s. Não diga que o circuito "
                f"funcionou: investigue (pinos, alimentação, código) ou espere mais.\n\nSaída até agora:\n{saida[-3000:]}")

    return StructuredTool.from_function(coroutine=esperar_serial, name="esperar_serial")


@asynccontextmanager
async def ferramentas_mcp():
    """Abre uma sessão por servidor e devolve as ferramentas (7 do bancada, 11 do Wokwi e esperar_serial).

    Uso: async with ferramentas_mcp() as ferramentas: ...

    O cliente.get_tools() sem sessão abre um processo novo a cada chamada de
    ferramenta: a simulação iniciada por wokwi_start_simulation morreria antes
    do wokwi_read_serial. Com a sessão aberta, o mesmo wokwi-cli atende todas as
    chamadas até o fim do bloco (uma resposta do agente).
    """
    cliente = MultiServerMCPClient(configuracao_servidores())
    async with AsyncExitStack() as pilha:
        ferramentas = []
        for nome in cliente.connections:
            sessao = await pilha.enter_async_context(cliente.session(nome))
            ferramentas += await load_mcp_tools(sessao, server_name=nome)
        ler_serial = next((f for f in ferramentas if f.name == "wokwi_read_serial"), None)
        if ler_serial:
            ferramentas.append(criar_esperar_serial(ler_serial))
        yield ferramentas
