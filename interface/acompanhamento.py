import json
import os
import re
from pathlib import Path

from agente.mcp_config import corrigir_acentos
from interface.painel import novidades

RAIZ = Path(__file__).resolve().parent.parent
PASTA_PROJETOS = Path(os.environ.get("PASTA_PROJETOS", RAIZ / "projetos"))

DOCUMENTOS = {
    "esp32-datasheet": "o datasheet do ESP32",
    "esp32-trm": "o manual técnico do ESP32",
    "esp32-hardware-design": "o guia de hardware do ESP32",
    "esp32-devkitc": "o guia da DevKitC",
    "dht22": "o datasheet do DHT22",
    "hc-sr04": "o datasheet do HC-SR04",
    "ssd1306": "o datasheet do SSD1306",
    "mpu6050": "o datasheet do MPU6050",
    "jlcpcb": "as regras da JLCPCB",
}


def rotulo(nome, args):
    args = args or {}
    if nome == "buscar_documentos":
        doc = args.get("documento")
        if doc and doc.startswith("wokwi-"):
            return f"Consultando a referência do Wokwi ({doc[6:]})"
        return f"Consultando {DOCUMENTOS.get(doc, 'os documentos')}"
    fixos = {
        "carregar_skill": f"Abrindo o roteiro {args.get('nome', '')}".strip(),
        "validar_diagrama": "Conferindo as ligações",
        "salvar_projeto": "Montando na bancada",
        "ler_projeto": "Lendo o projeto da bancada",
        "compilar": "Compilando o firmware",
        "wokwi_start_simulation": "Ligando a simulação",
        "esperar_serial": "Lendo a serial",
        "wokwi_read_serial": "Lendo a serial",
        "capturar_display": "Fotografando o display",
        "wokwi_stop_simulation": "Desligando a simulação",
        "wokwi_set_control": "Mexendo num controle da simulação",
        "wokwi_read_pin": "Medindo um pino",
        "resistor_led": "Calculando o resistor do LED",
        "divisor_tensao": "Calculando o divisor de tensão",
        "largura_trilha": "Calculando a largura da trilha",
        "gerar_bom": "Listando os materiais",
    }
    return fixos.get(nome, f"Usando {nome}")


def ler_diagrama(projeto):
    arquivo = PASTA_PROJETOS / projeto / "diagram.json" if projeto else None
    if not arquivo or not arquivo.exists():
        return None
    return json.loads(arquivo.read_text(encoding="utf-8"))


def serial_sem_boot(texto):
    """Tira o boot do ESP32 (até 'entry 0x...')."""
    texto = re.sub(r'^Texto ".*?" (encontrado|NÃO apareceu)[^\n]*\n+', "", texto)
    texto = re.sub(r"^Saída até agora:\n", "", texto, flags=re.M)
    return re.split(r"^entry 0x[0-9a-f]+\s*$", texto, flags=re.M)[-1].strip()


def _json(texto):
    try:
        return json.loads(texto)
    except (TypeError, json.JSONDecodeError):
        return {}


def registrar(conversa, nome, args, resultado, erro=False):
    """Devolve True se a bancada mudou."""
    args = args or {}
    etapas = conversa.setdefault("etapas", {})
    if nome == "salvar_projeto":
        r = _json(resultado)
        if "pasta" not in r:
            conversa["etapas"] = {"validado": False}
            return True
        projeto = args.get("nome")
        anterior = conversa.get("diagrama") if conversa.get("projeto") == projeto else None
        diagrama = ler_diagrama(projeto)
        conversa.update(projeto=projeto, titulo=projeto, diagrama=diagrama, serial="",
                        destaques=sorted(novidades(diagrama, anterior)) if anterior and diagrama else [],
                        etapas={"validado": True})
        return True
    if nome == "ler_projeto" and not erro and not conversa.get("projeto"):
        conversa.update(projeto=args.get("nome"), titulo=args.get("nome"), diagrama=ler_diagrama(args.get("nome")))
        return True
    if nome == "compilar":
        r = _json(resultado)
        etapas["compilado"] = bool(r.get("sucesso"))
        uso = " ".join(r.get("uso_memoria") or [])
        m = re.search(r"\((\d+)%\) of program storage", uso)
        etapas["memoria"] = f"{m.group(1)}% da flash" if m else ""
        etapas.pop("simulado", None)
        etapas.pop("serial_ok", None)
        return True
    if nome == "wokwi_start_simulation" and not erro:
        etapas["simulado"] = True
        return True
    if nome in ("esperar_serial", "wokwi_read_serial") and resultado:
        conversa["serial"] = serial_sem_boot(corrigir_acentos(resultado))
        if nome == "esperar_serial":
            etapas["serial_ok"] = "encontrado na serial" in resultado
        return True
    if nome == "capturar_display" and not erro:
        return True
    return False


def etapas_visiveis(etapas):
    if not etapas:
        return []
    itens = []
    if "validado" in etapas:
        itens.append(("Ligações conferidas", "ok") if etapas["validado"] else ("Ligações com erro", "erro"))
    if "compilado" in etapas:
        texto = "Compilado" + (f", {etapas['memoria']}" if etapas.get("memoria") else "")
        itens.append((texto, "ok") if etapas["compilado"] else ("Erro de compilação", "erro"))
    if etapas.get("simulado"):
        itens.append(("Simulado", "ok"))
    if "serial_ok" in etapas:
        itens.append(("Serial confirmada", "ok") if etapas["serial_ok"] else ("Serial sem o esperado", "erro"))
    return itens


def mover_peca(projeto, id, left, top, rotate=0):
    """Só mudam top, left e rotate, então não precisa validar de novo."""
    arquivo = PASTA_PROJETOS / projeto / "diagram.json" if projeto else None
    if not arquivo or not arquivo.exists():
        return False
    diagrama = json.loads(arquivo.read_text(encoding="utf-8"))
    for parte in diagrama.get("parts", []):
        if parte.get("id") == id:
            parte["left"], parte["top"] = round(float(left)), round(float(top))
            if rotate:
                parte["rotate"] = int(rotate) % 360
            else:
                parte.pop("rotate", None)
            arquivo.write_text(json.dumps(diagrama, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
    return False
