"""Fluxo completo pelos servidores MCP, sem o modelo: salvar, compilar, simular e ler a serial.

Precisa de WOKWI_CLI_TOKEN no .env, arduino-cli com o core esp32 e wokwi-cli.
Rodar com: pytest -m manual -s testes/test_mcp_manual.py
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from agente.mcp_config import RAIZ, ferramentas_mcp

load_dotenv(RAIZ / ".env")
EXEMPLO = RAIZ / "exemplos" / "teste-blink"

pytestmark = [
    pytest.mark.manual,
    pytest.mark.skipif(not os.environ.get("WOKWI_CLI_TOKEN"), reason="WOKWI_CLI_TOKEN não definido"),
]


def texto(resultado):
    """Conteúdo de uma ferramenta MCP: string ou lista de blocos de texto."""
    if isinstance(resultado, str):
        return resultado
    return "\n".join(b["text"] if isinstance(b, dict) else str(b) for b in resultado)


async def fluxo():
    async with ferramentas_mcp() as lista:
        f = {t.name: t for t in lista}
        nomes_bancada = {"validar_diagrama", "resistor_led", "divisor_tensao", "largura_trilha",
                         "gerar_bom", "salvar_projeto", "compilar"}
        assert nomes_bancada <= f.keys()
        assert {"wokwi_start_simulation", "wokwi_read_serial"} <= f.keys()
        assert len(lista) == 18, sorted(f)

        salvo = json.loads(texto(await f["salvar_projeto"].ainvoke({
            "nome": "teste-blink",
            "diagram_json": (EXEMPLO / "diagram.json").read_text(),
            "codigo": (EXEMPLO / "teste-blink.ino").read_text(),
        })))
        compilado = json.loads(texto(await f["compilar"].ainvoke({"projeto": "teste-blink"})))
        assert compilado["sucesso"], compilado

        inicio = texto(await f["wokwi_start_simulation"].ainvoke({"projectPath": salvo["pasta"]}))
        print("start:", inicio)
        serial = ""
        for _ in range(10):  # a serial chega aos poucos
            await asyncio.sleep(1)
            serial += texto(await f["wokwi_read_serial"].ainvoke({}))
            if "LED: APAGADO" in serial:
                break
        print("serial:", serial)
        return serial


def test_fluxo_salvar_compilar_simular_ler_serial():
    serial = asyncio.run(fluxo())
    assert "teste-blink iniciado" in serial
    assert "LED: ACESO" in serial
