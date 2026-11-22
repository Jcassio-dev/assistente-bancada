import asyncio

from langchain_core.tools import tool

from agente.mcp_config import criar_esperar_serial


def serial_falsa(saidas):
    @tool
    async def wokwi_read_serial() -> str:
        """Serial falsa: cada chamada devolve a próxima saída da lista."""
        return saidas.pop(0) if len(saidas) > 1 else saidas[0]

    return wokwi_read_serial


def test_espera_ate_o_texto_aparecer():
    ferramenta = criar_esperar_serial(serial_falsa(["boot", "boot\ninicio", "boot\ninicio\nTemperatura: 24"]), intervalo=0.01)
    r = asyncio.run(ferramenta.ainvoke({"texto": "temperatura", "segundos": 5}))
    assert r.startswith('Texto "temperatura" encontrado') and "Temperatura: 24" in r


def test_avisa_quando_o_texto_nao_aparece():
    ferramenta = criar_esperar_serial(serial_falsa(["boot\ninicio"]), intervalo=0.5)
    r = asyncio.run(ferramenta.ainvoke({"texto": "Temperatura", "segundos": 1}))
    assert "NÃO apareceu" in r and "Não diga que o circuito funcionou" in r and "inicio" in r
