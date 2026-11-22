"""Servidor MCP "bancada": ferramentas próprias para prototipar circuitos.

Roda via stdio:  python servidor_bancada/servidor.py
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PROJETOS = Path(os.environ.get("PASTA_PROJETOS", RAIZ / "projetos"))

mcp = FastMCP("bancada")

# O projeto suporta só o ESP32 (GPIOs de 3,3 V). Tipo no Wokwi -> FQBN do
# arduino-cli e sufixo do firmware gerado.
PLACAS = {
    "board-esp32-devkit-c-v4": {"fqbn": "esp32:esp32:esp32", "firmware": "ino.merged.bin"},
    "wokwi-esp32-devkit-v1": {"fqbn": "esp32:esp32:esp32", "firmware": "ino.merged.bin"},
}

# Pinos válidos de cada peça, copiados da saída do `wokwi-cli lint` (v0.29.1).
PINOS = {
    "board-esp32-devkit-c-v4": "0 2 3V3 4 5 5V 12 13 14 15 16 17 18 19 21 22 23 25 26 27 32 33 34 35 "
    "CLK CMD D0 D1 D2 D3 EN GND.1 GND.2 GND.3 RX TX VN VP",
    "wokwi-esp32-devkit-v1": "VIN GND.1 GND.2 D2 D4 D5 D12 D13 D14 D15 D18 D19 D21 D22 D23 D25 D26 D27 "
    "D32 D33 D34 D35 VN VP EN TX0 TX2 RX0 RX2 3V3",
    "wokwi-led": "A C",
    "wokwi-rgb-led": "COM R G B",
    "wokwi-resistor": "1 2",
    "wokwi-pushbutton": "1.l 2.l 1.r 2.r",
    "wokwi-slide-switch": "1 2 3",
    "wokwi-buzzer": "1 2",
    "wokwi-potentiometer": "GND SIG VCC",
    "wokwi-dht22": "VCC SDA NC GND",
    "wokwi-hc-sr04": "VCC TRIG ECHO GND",
    "wokwi-servo": "GND V+ PWM",
    "wokwi-photoresistor-sensor": "VCC GND DO AO",
    "wokwi-ntc-temperature-sensor": "VCC OUT GND",
    "board-ssd1306": "GND SCL SDA VCC",
}
PINOS = {tipo: set(pinos.split()) for tipo, pinos in PINOS.items()}

PINOS_5V = {"5V", "VIN"}
PINOS_3V3 = {"3V3"}
PINOS_ALIMENTACAO = {"VCC", "V+"}
# Pinos que saem da peça com a tensão de alimentação dela (perigosos se a peça
# estiver em 5 V e o pino for direto para um GPIO de 3,3 V).
PINOS_SAIDA = {
    "wokwi-hc-sr04": {"ECHO"},
    "wokwi-potentiometer": {"SIG"},
    "wokwi-dht22": {"SDA"},
    "wokwi-photoresistor-sensor": {"DO", "AO"},
    "wokwi-ntc-temperature-sensor": {"OUT"},
    "board-ssd1306": {"SDA"},
}

DESCRICOES = {
    "board-esp32-devkit-c-v4": "Placa ESP32 DevKitC V4",
    "wokwi-esp32-devkit-v1": "Placa ESP32 DevKit V1",
    "wokwi-led": "LED",
    "wokwi-rgb-led": "LED RGB",
    "wokwi-resistor": "Resistor",
    "wokwi-pushbutton": "Botão (push button)",
    "wokwi-slide-switch": "Chave deslizante",
    "wokwi-buzzer": "Buzzer",
    "wokwi-potentiometer": "Potenciômetro",
    "wokwi-dht22": "Sensor de temperatura e umidade DHT22",
    "wokwi-hc-sr04": "Sensor ultrassônico HC-SR04",
    "wokwi-servo": "Servo motor",
    "wokwi-photoresistor-sensor": "Módulo LDR",
    "wokwi-ntc-temperature-sensor": "Sensor de temperatura NTC",
    "board-ssd1306": "Display OLED SSD1306",
}

SERIE_E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]


def _e12_acima(valor):
    """Menor valor comercial da série E12 que seja >= valor (em ohms)."""
    decada = 1.0
    while decada * 10 <= valor:
        decada *= 10
    while True:
        for base in SERIE_E12:
            candidato = round(base * decada, 6)
            if candidato >= valor - 1e-9:
                return candidato
        decada *= 10


def _formatar_ohms(valor):
    if valor >= 1e6:
        return f"{valor / 1e6:g} MΩ"
    if valor >= 1e3:
        return f"{valor / 1e3:g} kΩ"
    return f"{valor:g} Ω"


def _ler_diagrama(diagram_json):
    """Converte o texto em dict; devolve (diagrama, mensagem_de_erro)."""
    try:
        diagrama = json.loads(diagram_json)
    except json.JSONDecodeError as e:
        return None, f"JSON inválido: {e}"
    if not isinstance(diagrama, dict) or "parts" not in diagrama:
        return None, "O diagrama precisa ser um objeto com a lista 'parts'."
    return diagrama, None


def _placa_do_diagrama(diagrama):
    for parte in diagrama.get("parts", []):
        if parte.get("type") in PLACAS:
            return parte
    return None


class _Redes:
    """Agrupa pinos ligados entre si (union-find simples)."""

    def __init__(self):
        self.pai = {}

    def raiz(self, no):
        self.pai.setdefault(no, no)
        while self.pai[no] != no:
            no = self.pai[no]
        return no

    def unir(self, a, b):
        self.pai[self.raiz(a)] = self.raiz(b)

    def membros(self, no):
        r = self.raiz(no)
        return [n for n in list(self.pai) if self.raiz(n) == r]


@mcp.tool()
def validar_diagrama(diagram_json: str) -> dict:
    """Confere um diagram.json do Wokwi antes de simular.

    Procura: pino inexistente, peça inexistente, LED sem resistor, GND de peça
    sem ligação com o GND da placa, 5 V ligado direto em pino de 3,3 V e sinal
    de peça alimentada com 5 V entrando em GPIO de 3,3 V.
    Devolve {"valido": bool, "erros": [...], "avisos": [...]}.
    """
    diagrama, erro = _ler_diagrama(diagram_json)
    if erro:
        return {"valido": False, "erros": [erro], "avisos": []}

    tipos = {p["id"]: p["type"] for p in diagrama["parts"]}
    erros, avisos = [], []
    redes = _Redes()

    for tipo in sorted(set(tipos.values()) - PINOS.keys()):
        avisos.append(f"Tipo '{tipo}' não está na tabela de peças: pinos não verificados.")

    for conexao in diagrama.get("connections", []):
        pontas = conexao[:2]
        ok = True
        for ponta in pontas:
            if ponta.startswith("$"):  # $serialMonitor
                continue
            id_parte, _, pino = ponta.partition(":")
            if id_parte not in tipos:
                erros.append(f"Conexão '{ponta}': a peça '{id_parte}' não existe no diagrama.")
                ok = False
            elif tipos[id_parte] in PINOS and pino not in PINOS[tipos[id_parte]]:
                validos = ", ".join(sorted(PINOS[tipos[id_parte]]))
                erros.append(
                    f"Pino '{pino}' não existe em '{id_parte}' ({tipos[id_parte]}). Pinos válidos: {validos}."
                )
                ok = False
        if ok and not any(p.startswith("$") for p in pontas):
            redes.unir(*pontas)

    def tipo_de(no):
        return tipos.get(no.split(":")[0])

    def pino_de(no):
        return no.split(":", 1)[1]

    placas = [i for i, t in tipos.items() if t in PLACAS]
    if not placas:
        avisos.append("Nenhum microcontrolador conhecido no diagrama.")
    gnds_placa = [f"{i}:{p}" for i in placas for p in PINOS[tipos[i]] if p.startswith("GND")]

    def ligado_ao_gnd(no):
        return any(redes.raiz(no) == redes.raiz(g) for g in gnds_placa)

    # LEDs: cada pino de cor precisa de um resistor na mesma rede (anodo ou catodo).
    for id_parte, tipo in tipos.items():
        if tipo == "wokwi-led":
            pinos_led = [(f"{id_parte}:A", f"{id_parte}:C")]
        elif tipo == "wokwi-rgb-led":
            pinos_led = [(f"{id_parte}:{cor}", f"{id_parte}:COM") for cor in "RGB"]
        else:
            continue
        for sinal, comum in pinos_led:
            vizinhos = redes.membros(sinal) + redes.membros(comum)
            if len(redes.membros(sinal)) == 1 or len(redes.membros(comum)) == 1:
                avisos.append(f"LED '{id_parte}': pino {pino_de(sinal)} ou {pino_de(comum)} está desconectado.")
            elif not any(tipo_de(n) == "wokwi-resistor" for n in vizinhos):
                erros.append(f"LED '{id_parte}' (pino {pino_de(sinal)}) está sem resistor em série.")

    # GND: placa ligada a algo e GND de cada peça ligado ao GND da placa.
    if placas and len(tipos) > 1 and not any(len(redes.membros(g)) > 1 for g in gnds_placa):
        erros.append("Nenhum pino GND da placa está ligado ao circuito.")
    for id_parte, tipo in tipos.items():
        if tipo in PLACAS:
            continue
        for pino in sorted(PINOS.get(tipo, ())):
            if pino.startswith("GND") and placas and not ligado_ao_gnd(f"{id_parte}:{pino}"):
                erros.append(f"O {pino} de '{id_parte}' não está ligado ao GND da placa.")

    # 5 V em pinos de placas de 3,3 V.
    for rede in {redes.raiz(n): redes.membros(n) for n in list(redes.pai)}.values():
        tem_5v = [n for n in rede if tipo_de(n) in PLACAS and pino_de(n) in PINOS_5V]
        if not tem_5v:
            continue
        for n in rede:
            t = tipo_de(n)
            if t in PLACAS and pino_de(n) not in PINOS_5V and not pino_de(n).startswith("GND"):
                erros.append(f"{tem_5v[0]} (5 V) está ligado direto em {n}, que é de 3,3 V.")

    # Peça alimentada com 5 V mandando sinal direto para GPIO de 3,3 V (ex.: ECHO do HC-SR04).
    for id_parte, tipo in tipos.items():
        if tipo not in PINOS_SAIDA:
            continue
        alimentacao = [f"{id_parte}:{p}" for p in PINOS[tipo] if p in PINOS_ALIMENTACAO]
        if not any(pino_de(n) in PINOS_5V for a in alimentacao for n in redes.membros(a) if tipo_de(n) in PLACAS):
            continue
        for pino in sorted(PINOS_SAIDA[tipo]):
            for n in redes.membros(f"{id_parte}:{pino}"):
                t = tipo_de(n)
                if t in PLACAS and pino_de(n) not in PINOS_5V | PINOS_3V3:
                    avisos.append(
                        f"'{id_parte}' é alimentado com 5 V e o pino {pino} vai direto em {n} (3,3 V). "
                        "Use um divisor de tensão ou conversor de nível."
                    )

    return {"valido": not erros, "erros": erros, "avisos": avisos}


@mcp.tool()
def resistor_led(tensao_fonte: float, tensao_led: float = 2.0, corrente_ma: float = 10.0) -> dict:
    """Calcula o resistor em série de um LED: R = (Vfonte - Vled) / I.

    tensao_led é a queda direta do LED (vermelho ~2 V, azul/branco ~3 V).
    Devolve o valor ideal, o valor comercial E12 logo acima, a corrente real e
    a potência dissipada no resistor.
    """
    if corrente_ma <= 0:
        return {"erro": "A corrente precisa ser maior que zero."}
    if tensao_fonte <= tensao_led:
        return {"erro": "A tensão da fonte precisa ser maior que a queda do LED."}
    r_ideal = (tensao_fonte - tensao_led) / (corrente_ma / 1000)
    r_comercial = _e12_acima(r_ideal)
    corrente_real = (tensao_fonte - tensao_led) / r_comercial * 1000
    potencia_mw = (tensao_fonte - tensao_led) * corrente_real
    return {
        "resistor_ideal_ohms": round(r_ideal, 1),
        "resistor_comercial_ohms": r_comercial,
        "resistor_comercial": _formatar_ohms(r_comercial),
        "corrente_real_ma": round(corrente_real, 2),
        "potencia_resistor_mw": round(potencia_mw, 1),
        "potencia_minima_resistor": "1/4 W" if potencia_mw < 125 else "1/2 W ou maior",
    }


@mcp.tool()
def divisor_tensao(tensao_entrada: float, tensao_saida: float, r2_ohms: float = 10000) -> dict:
    """Dimensiona um divisor resistivo: Vout = Vin * R2 / (R1 + R2).

    Recebe R2 (resistor ligado ao GND) e calcula R1. O R1 comercial (E12) é
    arredondado para cima, então a saída real nunca passa da desejada — útil
    para baixar 5 V para um GPIO de 3,3 V.
    """
    if not 0 < tensao_saida < tensao_entrada:
        return {"erro": "A tensão de saída precisa ficar entre 0 e a tensão de entrada."}
    if r2_ohms <= 0:
        return {"erro": "R2 precisa ser maior que zero."}
    r1_ideal = r2_ohms * (tensao_entrada - tensao_saida) / tensao_saida
    r1 = _e12_acima(r1_ideal)
    saida_real = tensao_entrada * r2_ohms / (r1 + r2_ohms)
    return {
        "r1_ideal_ohms": round(r1_ideal, 1),
        "r1_comercial_ohms": r1,
        "r1_comercial": _formatar_ohms(r1),
        "r2_ohms": r2_ohms,
        "tensao_saida_real": round(saida_real, 3),
        "corrente_ma": round(tensao_entrada / (r1 + r2_ohms) * 1000, 3),
    }


@mcp.tool()
def largura_trilha(
    corrente: float,
    espessura_cobre: float = 1.0,
    elevacao_temperatura: float = 10.0,
    camada: str = "externa",
) -> dict:
    """Largura mínima de trilha pela IPC-2221.

    corrente em A, espessura_cobre em oz/ft² (1 oz = 35 µm), elevação de
    temperatura em °C, camada "externa" ou "interna".
    A[mil²] = (I / (k * ΔT^0,44))^(1/0,725), k = 0,048 (externa) ou 0,024 (interna).
    """
    if corrente <= 0 or espessura_cobre <= 0 or elevacao_temperatura <= 0:
        return {"erro": "Corrente, espessura e elevação de temperatura precisam ser maiores que zero."}
    if camada not in ("externa", "interna"):
        return {"erro": "camada deve ser 'externa' ou 'interna'."}
    k = 0.048 if camada == "externa" else 0.024
    area_mils2 = (corrente / (k * elevacao_temperatura**0.44)) ** (1 / 0.725)
    largura_mils = area_mils2 / (espessura_cobre * 1.378)
    return {
        "largura_mm": round(largura_mils * 0.0254, 3),
        "largura_mils": round(largura_mils, 1),
        "area_secao_mils2": round(area_mils2, 1),
        "parametros": f"{corrente} A, {espessura_cobre} oz, ΔT {elevacao_temperatura} °C, camada {camada}",
        "observacao": "Valor mínimo pela IPC-2221; confira também a largura mínima do fabricante.",
    }


@mcp.tool()
def gerar_bom(diagram_json: str) -> dict:
    """Gera a lista de materiais (BOM) a partir de um diagram.json do Wokwi.

    Agrupa peças iguais (mesmo tipo e mesmo valor/cor) e lista as referências.
    """
    diagrama, erro = _ler_diagrama(diagram_json)
    if erro:
        return {"erro": erro}
    grupos = {}
    for parte in diagrama["parts"]:
        tipo = parte["type"]
        attrs = parte.get("attrs", {})
        descricao = DESCRICOES.get(tipo, tipo)
        if tipo == "wokwi-resistor":
            descricao += " " + _formatar_ohms(float(attrs.get("value", 1000)))
        elif tipo == "wokwi-led":
            descricao += " " + attrs.get("color", "red")
        grupo = grupos.setdefault(descricao, {"quantidade": 0, "descricao": descricao, "tipo": tipo, "referencias": []})
        grupo["quantidade"] += 1
        grupo["referencias"].append(parte["id"])
    itens = sorted(grupos.values(), key=lambda g: g["descricao"])
    return {"itens": itens, "total_pecas": sum(g["quantidade"] for g in itens)}


def _pasta_projeto(nome):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", nome):
        return None, "Nome inválido: use só letras minúsculas, números, '-' e '_' (ex.: 'estacao-dht22')."
    return PASTA_PROJETOS / nome, None


REGEX_PONTO_FIO = re.compile(r"^(\*|[hv]-?\d+(\.\d+)?)$")


def _limpar_pontos_dos_fios(diagrama):
    """Remove pontos de fio fora do formato do Wokwi ("h10", "v-20", "*"). Só mudam o desenho."""
    for conexao in diagrama.get("connections", []):
        if len(conexao) >= 4 and isinstance(conexao[3], list):
            conexao[3] = [p for p in conexao[3] if isinstance(p, str) and REGEX_PONTO_FIO.match(p)]


@mcp.tool()
def salvar_projeto(nome: str, diagram_json: str, codigo: str) -> dict:
    """Salva um projeto em projetos/<nome>/: sketch .ino, diagram.json e wokwi.toml.

    Roda o validar_diagrama antes e não salva se houver erros.
    O wokwi.toml aponta para o firmware em build/, gerado pela ferramenta compilar.
    Devolve a pasta do projeto, que é o projectPath do wokwi_start_simulation.
    """
    pasta, erro = _pasta_projeto(nome)
    if erro:
        return {"erro": erro}
    diagrama, erro = _ler_diagrama(diagram_json)
    if erro:
        return {"erro": erro}
    placa = _placa_do_diagrama(diagrama)
    if placa is None:
        return {"erro": f"Nenhuma placa suportada no diagrama. O projeto trabalha só com ESP32: {', '.join(PLACAS)}."}
    validacao = validar_diagrama(diagram_json)
    if not validacao["valido"]:
        return {"erro": "O diagrama tem erros. Corrija e chame salvar_projeto de novo.",
                "erros": validacao["erros"], "avisos": validacao["avisos"]}
    _limpar_pontos_dos_fios(diagrama)

    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{nome}.ino").write_text(codigo, encoding="utf-8")
    (pasta / "diagram.json").write_text(json.dumps(diagrama, indent=2, ensure_ascii=False), encoding="utf-8")
    sufixo = PLACAS[placa["type"]]["firmware"]
    (pasta / "wokwi.toml").write_text(
        f'[wokwi]\nversion = 1\nfirmware = "build/{nome}.{sufixo}"\nelf = "build/{nome}.ino.elf"\n',
        encoding="utf-8",
    )
    return {
        "pasta": str(pasta),
        "arquivos": [f"{nome}.ino", "diagram.json", "wokwi.toml"],
        "placa": placa["type"],
        "avisos_validacao": validacao["avisos"],
        "proximo_passo": f"compilar('{nome}') e depois wokwi_start_simulation(projectPath='{pasta}')",
    }


REGEX_ERRO_GCC = re.compile(
    r"^(?P<arquivo>[^\s:][^:\n]*):(?P<linha>\d+):(?:(?P<coluna>\d+):)? (?:fatal )?error: (?P<mensagem>.+)$",
    re.MULTILINE,
)


def resumir_erros_compilacao(saida: str, limite: int = 10) -> dict:
    """Extrai da saída do arduino-cli os erros no formato arquivo:linha:coluna."""
    erros, vistos = [], set()
    for m in REGEX_ERRO_GCC.finditer(saida):
        erro = {
            "arquivo": Path(m["arquivo"]).name,
            "linha": int(m["linha"]),
            "coluna": int(m["coluna"]) if m["coluna"] else None,
            "mensagem": m["mensagem"].strip(),
        }
        chave = (erro["arquivo"], erro["linha"], erro["mensagem"])
        if chave not in vistos:
            vistos.add(chave)
            erros.append(erro)
    resumo = {"erros": erros[:limite], "total_erros": len(erros)}
    if any("No such file or directory" in e["mensagem"] and ".h" in e["mensagem"] for e in erros):
        resumo["dica"] = "Biblioteca faltando: instale com `arduino-cli lib install \"<nome>\"` ou troque o include."
    if not erros:
        # Erro fora do compilador (core não instalado, FQBN errado...): últimas linhas.
        linhas = [l for l in saida.splitlines() if l.strip()]
        resumo["saida"] = linhas[-15:]
    return resumo


@mcp.tool()
def compilar(projeto: str) -> dict:
    """Compila projetos/<projeto> com o arduino-cli (FQBN deduzido da placa no diagram.json).

    Em caso de sucesso, o firmware fica em build/ e o projeto pode ser simulado.
    Em caso de falha, devolve os erros (arquivo, linha, mensagem) para corrigir o código.
    """
    pasta, erro = _pasta_projeto(projeto)
    if erro:
        return {"sucesso": False, "erro": erro}
    if not (pasta / f"{projeto}.ino").exists() or not (pasta / "diagram.json").exists():
        return {"sucesso": False, "erro": f"Projeto '{projeto}' não encontrado. Salve antes com salvar_projeto."}
    diagrama, erro = _ler_diagrama((pasta / "diagram.json").read_text(encoding="utf-8"))
    placa = _placa_do_diagrama(diagrama) if diagrama else None
    if placa is None:
        return {"sucesso": False, "erro": erro or "Nenhuma placa suportada no diagram.json."}
    arduino_cli = os.environ.get("ARDUINO_CLI") or shutil.which("arduino-cli")
    if not arduino_cli:
        return {"sucesso": False, "erro": "arduino-cli não encontrado no PATH."}

    fqbn = PLACAS[placa["type"]]["fqbn"]
    comando = [arduino_cli, "compile", "--fqbn", fqbn, "--output-dir", str(pasta / "build"), str(pasta)]
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"sucesso": False, "erro": "A compilação passou de 10 minutos e foi interrompida."}

    if resultado.returncode != 0:
        return {"sucesso": False, "fqbn": fqbn, **resumir_erros_compilacao(resultado.stderr + resultado.stdout)}
    uso = [l for l in resultado.stdout.splitlines() if l.startswith(("Sketch uses", "Global variables"))]
    return {
        "sucesso": True,
        "fqbn": fqbn,
        "firmware": str(pasta / "build" / f"{projeto}.{PLACAS[placa['type']]['firmware']}"),
        "uso_memoria": uso,
    }


if __name__ == "__main__":
    mcp.run()
