"""Uso: python scripts/avaliar_rag.py [--modo denso|hibrido|ambos] [--k 5] [--resumo]"""

import argparse
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.rag import buscar, colecao  # noqa: E402

# As perguntas em inglês são como o agente vai reformular; as em português
# entram como o usuário escreveria, sem tradução.
PERGUNTAS = [
    {
        "pergunta": "What is the maximum source current of an ESP32 GPIO pin?",
        "documentos": ["esp32-datasheet"],
        "fato": r"IOH.*40|source current.*40 ?mA",
        "termo_exato": False,
    },
    {
        "pergunta": "What happens to GPIO12 (MTDI) during boot? strapping pin",
        "documentos": ["esp32-datasheet", "esp32-hardware-design"],
        "fato": r"MTDI.*(VDD_SDIO|1\.8 ?V|flash)|(VDD_SDIO|flash voltage).*MTDI|GPIO12.*(VDD_SDIO|1\.8 ?V)",
        "termo_exato": True,
    },
    {
        "pergunta": "Which ESP32 GPIOs are input-only (GPIO34 to GPIO39)?",
        "documentos": ["esp32-datasheet", "esp32-trm", "esp32-hardware-design", "esp32-devkitc"],
        "fato": r"(input[- ]only|only.{0,20}input).{0,200}(34|GPI)|(34|39).{0,200}(input[- ]only|only.{0,20}input)",
        "termo_exato": True,
    },
    {
        "pergunta": "Why can't ADC2 be used when Wi-Fi is enabled?",
        "documentos": ["esp32-datasheet", "esp32-trm", "esp32-hardware-design", "wokwi-esp32"],
        "fato": r"ADC2.{0,250}Wi-?Fi|Wi-?Fi.{0,250}ADC2",
        "termo_exato": True,
    },
    {
        "pergunta": "Qual é a faixa de tensão de alimentação do sensor DHT22?",
        "documentos": ["dht22", "wokwi-dht22"],
        "fato": r"3\.3.{0,15}(6|5\.5) ?V|power supply.{0,40}3\.3",
        "termo_exato": False,
    },
    {
        "pergunta": "Qual a largura mínima de trilha e espaçamento que a JLCPCB fabrica numa placa de 2 camadas?",
        "documentos": ["jlcpcb"],
        "fato": r"track width.{0,80}0\.10",
        "termo_exato": False,
    },
    {
        "pergunta": "SSD1306 OLED in Wokwi: which pins and what is the default I2C address?",
        "documentos": ["wokwi-ssd1306", "ssd1306"],
        "fato": r"0x3c",
        "termo_exato": False,
    },
    {
        "pergunta": "ESP32 power consumption in deep-sleep mode",
        "documentos": ["esp32-datasheet"],
        "fato": r"deep-?sleep.{0,200}µA",
        "termo_exato": False,
    },
]


def relevante(trecho, p):
    return trecho["documento"] in p["documentos"] and re.search(p["fato"], trecho["texto"], re.S | re.I) is not None


def relevantes_no_indice(p):
    todos = colecao().get(include=["documents", "metadatas"])
    return sum(relevante({"texto": d, **m}, p) for d, m in zip(todos["documents"], todos["metadatas"]))


def avaliar(modo, k, mostrar_trechos=True):
    resultados = []
    for n, p in enumerate(PERGUNTAS, 1):
        trechos = buscar(p["pergunta"], k=k, modo=modo)
        posicoes = [i for i, t in enumerate(trechos, 1) if relevante(t, p)]
        resultados.append(posicoes[0] if posicoes else None)
        if not mostrar_trechos:
            continue
        marca = "termo exato" if p["termo_exato"] else ""
        print(f"\n[{n}] {p['pergunta']}  {marca}")
        for i, t in enumerate(trechos, 1):
            pagina = f"p.{t['pagina']}" if t["pagina"] else "web"
            estrela = "*" if i in posicoes else " "
            trecho = re.sub(r"\s+", " ", t["texto"])[:160]
            print(f"  {estrela}{i}. {t['pontuacao']:.3f} {t['documento']:22} {pagina:6} [{t['secao'][:40]}] {trecho}")
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modo", default="ambos", choices=["denso", "hibrido", "ambos"])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--resumo", action="store_true", help="só a tabela final")
    args = ap.parse_args()
    modos = ["denso", "hibrido"] if args.modo == "ambos" else [args.modo]

    tabela = {}
    for modo in modos:
        if not args.resumo:
            print(f"\n{'=' * 30} modo {modo} {'=' * 30}")
        tabela[modo] = avaliar(modo, args.k, not args.resumo)

    print(f"\nPosição do primeiro trecho relevante (top {args.k}; '-' = não recuperado)")
    print(f"{'#':>2}  {'pergunta':60} " + " ".join(f"{m:>8}" for m in modos) + "  no índice")
    for n, p in enumerate(PERGUNTAS):
        celulas = " ".join(f"{(tabela[m][n] or '-'):>8}" for m in modos)
        print(f"{n + 1:>2}  {p['pergunta'][:60]:60} {celulas}  {relevantes_no_indice(p):>9}")
    for m in modos:
        acertos = sum(1 for r in tabela[m] if r)
        mrr = sum(1 / r for r in tabela[m] if r) / len(PERGUNTAS)
        print(f"{m}: {acertos}/{len(PERGUNTAS)} perguntas com trecho relevante no top {args.k}, MRR = {mrr:.2f}")


if __name__ == "__main__":
    main()
