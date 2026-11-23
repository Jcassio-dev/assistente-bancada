"""Simulação ao vivo.

Roda numa thread com laço asyncio próprio para sobreviver às reexecuções do
Streamlit. Desliga sozinha depois de LIMITE_SEGUNDOS ou OCIOSA_SEGUNDOS sem uso.
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
INTERVALO = 0.3

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
    return [(p["id"], p["type"], CONTROLES.get(p["type"], []))
            for p in (diagrama or {}).get("parts", [])
            if p["type"] in CONTROLES or p["type"] in BOTOES]


def leds_do_diagrama(diagrama):
    return [p["id"] for p in (diagrama or {}).get("parts", []) if p["type"] == "wokwi-led"]


def _pino_ligado(texto):
    return ": true" in texto


class SimulacaoAoVivo:
    def __init__(self, projeto, pasta, leds):
        self.projeto, self.pasta, self.leds = projeto, str(pasta), leds
        self.comandos = queue.Queue()
        self.serial = ""
        self.acesos = {}
        self.erro = None
        self.ativa = False
        self.iniciando = True
        self.inicio = time.time()
        self.ultima_consulta = time.time()
        self.thread = threading.Thread(target=lambda: asyncio.run(self._rodar()), daemon=True)
        self.thread.start()


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
                        break
                    if await self._atender_comandos(f):
                        break
                    novo = texto_ferramenta(await f["wokwi_read_serial"].ainvoke({"clear": True}))
                    if novo.strip() != "No serial output":  # resposta do Wokwi quando nada chegou
                        self.serial = (self.serial + novo.replace("\r", ""))[-6000:]
                    for led in self.leds:
                        # o catodo vai ao GND (direto ou pelo resistor): basta ler o anodo
                        anodo = texto_ferramenta(await f["wokwi_read_pin"].ainvoke({"partId": led, "pin": "A"}))
                        self.acesos[led] = _pino_ligado(anodo)
                    await asyncio.sleep(INTERVALO)
                await f["wokwi_stop_simulation"].ainvoke({})
        except Exception as e:
            self.erro = f"Não foi possível simular: {e}"
        finally:
            self.ativa = self.iniciando = False

    async def _atender_comandos(self, f):
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
