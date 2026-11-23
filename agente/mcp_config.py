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
    ambiente = dict(os.environ)
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
    if not isinstance(resultado, str):
        resultado = "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in resultado)
    return corrigir_acentos(resultado)


def corrigir_acentos(texto):
    """A serial do Wokwi chega com UTF-8 lido como Latin-1 ("Â°C")."""
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def criar_esperar_serial(ler_serial, intervalo=1.0):
    """O wokwi_read_serial só devolve o que já chegou: lido logo após o boot vinha vazio."""

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
    """Uma sessão por servidor, aberta durante a resposta inteira.

    Sem sessão, cada chamada abre um wokwi-cli novo e a simulação morre antes do
    wokwi_read_serial.
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
