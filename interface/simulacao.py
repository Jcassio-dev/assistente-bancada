"""Simulação ao vivo na bancada: o usuário liga, mexe nos controles e vê a serial e os LEDs.

O Streamlit reexecuta o script a cada interação, mas a simulação precisa continuar
entre uma reexecução e outra. Por isso cada simulação roda numa thread com o seu
próprio laço asyncio, que mantém aberta uma sessão MCP com o `wokwi-cli` e recebe
comandos por uma fila. A interface só lê o estado (serial, pinos) e envia comandos.

Para não gastar minutos do Wokwi à toa, a simulação desliga sozinha depois de
LIMITE_SEGUNDOS ligada ou de OCIOSA_SEGUNDOS sem a página perguntar pelo estado.
"""

import asyncio
import queue
import threading
import time

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from agente.mcp_config import configuracao_servidores, texto_ferramenta

LIMITE_SEGUNDOS = 180
OCIOSA_SEGUNDOS = 20
INTERVALO = 0.8

# Controles de simulação de cada peça: (controle, rótulo, mínimo, máximo, passo, valor inicial).
CONTROLES = {
    "wokwi-dht22": [("temperature", "Temperatura (°C)", -40.0, 80.0, 0.5, 24.0),
                    ("humidity", "Umidade (%)", 0.0, 100.0, 1.0, 40.0)],
    "wokwi-hc-sr04": [("distance", "Distância (cm)", 2.0, 400.0, 1.0, 400.0)],
    "wokwi-potentiometer": [("position", "Posição", 0.0, 1.0, 0.01, 0.0)],
    "wokwi-ntc-temperature-sensor": [("temperature", "Temperatura (°C)", -24.0, 80.0, 0.5, 24.0)],
    "wokwi-photoresistor-sensor": [("lux", "Luz (lux)", 0.1, 100000.0, 10.0, 500.0)],
}
BOTOES = {"wokwi-pushbutton"}  # controle "pressed": 1 aperta, 0 solta


def controles_do_diagrama(diagrama):
    """[(id da peça, tipo, [controles])] das peças que têm controle na simulação."""
    return [(p["id"], p["type"], CONTROLES.get(p["type"], []))
            for p in (diagrama or {}).get("parts", [])
            if p["type"] in CONTROLES or p["type"] in BOTOES]


def leds_do_diagrama(diagrama):
    return [p["id"] for p in (diagrama or {}).get("parts", []) if p["type"] == "wokwi-led"]


def _pino_ligado(texto):
    """'Pin A on led1: true (undefinedV)' -> True."""
    return ": true" in texto


class SimulacaoAoVivo:
    def __init__(self, projeto, pasta, leds):
        self.projeto, self.pasta, self.leds = projeto, str(pasta), leds
        self.comandos = queue.Queue()
        self.serial = ""
        self.acesos = {}  # id do LED -> bool
        self.erro = None
        self.ativa = False
        self.iniciando = True
        self.inicio = time.time()
        self.ultima_consulta = time.time()
        self.thread = threading.Thread(target=lambda: asyncio.run(self._rodar()), daemon=True)
        self.thread.start()

    # ---- chamados pela interface ----

    def estado(self):
        self.ultima_consulta = time.time()
        restante = max(0, int(LIMITE_SEGUNDOS - (time.time() - self.inicio)))
        return {"ativa": self.ativa, "iniciando": self.iniciando, "erro": self.erro,
                "serial": self.serial, "acesos": dict(self.acesos), "restante": restante}

    def controlar(self, parte, controle, valor):
        self.comandos.put(("controle", parte, controle, float(valor)))

    def apertar(self, parte):
        self.comandos.put(("botao", parte))

    def parar(self):
        self.comandos.put(("parar",))

    # ---- thread da simulação ----

    async def _rodar(self):
        cliente = MultiServerMCPClient({"wokwi": configuracao_servidores()["wokwi"]})
        try:
            async with cliente.session("wokwi") as sessao:
                f = {t.name: t for t in await load_mcp_tools(sessao)}
                await f["wokwi_start_simulation"].ainvoke({"projectPath": self.pasta})
                self.ativa, self.iniciando = True, False
                while True:
                    if time.time() - self.inicio > LIMITE_SEGUNDOS:
                        self.erro = f"Simulação desligada depois de {LIMITE_SEGUNDOS // 60} minutos."
                        break
                    if time.time() - self.ultima_consulta > OCIOSA_SEGUNDOS:
                        break  # a página foi fechada
                    if await self._atender_comandos(f):
                        break
                    self.serial = (self.serial + texto_ferramenta(
                        await f["wokwi_read_serial"].ainvoke({"clear": True})).replace("\r", ""))[-6000:]
                    for led in self.leds:
                        anodo = texto_ferramenta(await f["wokwi_read_pin"].ainvoke({"partId": led, "pin": "A"}))
                        catodo = texto_ferramenta(await f["wokwi_read_pin"].ainvoke({"partId": led, "pin": "C"}))
                        self.acesos[led] = _pino_ligado(anodo) and not _pino_ligado(catodo)
                    await asyncio.sleep(INTERVALO)
                await f["wokwi_stop_simulation"].ainvoke({})
        except Exception as e:  # token ausente, projeto não compilado, wokwi-cli fora do ar
            self.erro = f"Não foi possível simular: {e}"
        finally:
            self.ativa = self.iniciando = False

    async def _atender_comandos(self, f):
        """Executa os comandos pendentes. Devolve True se pediram para parar."""
        while not self.comandos.empty():
            comando = self.comandos.get_nowait()
            if comando[0] == "parar":
                return True
            if comando[0] == "controle":
                _, parte, controle, valor = comando
                await f["wokwi_set_control"].ainvoke({"partId": parte, "control": controle, "value": valor})
            elif comando[0] == "botao":
                await f["wokwi_set_control"].ainvoke({"partId": comando[1], "control": "pressed", "value": 1})
                await asyncio.sleep(0.25)
                await f["wokwi_set_control"].ainvoke({"partId": comando[1], "control": "pressed", "value": 0})
        return False
