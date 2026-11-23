"""Uso: python scripts/listar_ferramentas_wokwi.py [pasta_do_projeto]"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.mcp_config import caminho_wokwi_cli  # noqa: E402


async def main():
    load_dotenv(RAIZ / ".env")
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        sys.exit("Defina WOKWI_CLI_TOKEN antes de rodar.")

    pasta = sys.argv[1] if len(sys.argv) > 1 else str(RAIZ / "exemplos/teste-blink")
    cliente = MultiServerMCPClient(
        {
            "wokwi": {
                "transport": "stdio",
                "command": caminho_wokwi_cli(),
                "args": ["mcp", "--quiet", pasta],
                # o processo filho precisa herdar o token e o PATH
                "env": dict(os.environ),
            }
        }
    )
    ferramentas = await cliente.get_tools()
    print(f"{len(ferramentas)} ferramentas no servidor wokwi:\n")
    for f in ferramentas:
        print(f"- {f.name}: {f.description}")
        print(f"    argumentos: {list(f.args)}")


if __name__ == "__main__":
    asyncio.run(main())
