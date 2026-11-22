"""Testes das funções puras do servidor bancada."""

import json
from pathlib import Path

import pytest

from servidor_bancada import servidor
from servidor_bancada.servidor import (
    divisor_tensao,
    gerar_bom,
    largura_trilha,
    resistor_led,
    resumir_erros_compilacao,
    salvar_projeto,
    validar_diagrama,
)

EXEMPLO = Path(__file__).resolve().parent.parent / "exemplos" / "teste-blink"


def diagrama(partes, conexoes):
    return json.dumps(
        {
            "version": 1,
            "parts": [{"type": t, "id": i, "attrs": a} for i, t, a in partes],
            "connections": [[a, b, "", []] for a, b in conexoes],
        }
    )


ESP = ("esp", "board-esp32-devkit-c-v4", {})
LED = ("led1", "wokwi-led", {"color": "red"})
R1 = ("r1", "wokwi-resistor", {"value": "220"})


# ---------- validar_diagrama ----------

def test_exemplo_blink_e_valido():
    r = validar_diagrama((EXEMPLO / "diagram.json").read_text())
    assert r["valido"], r["erros"]
    assert r["erros"] == []


def test_json_invalido():
    r = validar_diagrama("{ isso não é json")
    assert not r["valido"]
    assert "JSON inválido" in r["erros"][0]


def test_pino_inexistente():
    d = diagrama([ESP, LED, R1], [("esp:99", "r1:1"), ("r1:2", "led1:A"), ("led1:C", "esp:GND.1")])
    r = validar_diagrama(d)
    assert not r["valido"]
    assert any("Pino '99' não existe em 'esp'" in e for e in r["erros"])


def test_peca_inexistente():
    d = diagrama([ESP], [("esp:2", "fantasma:1")])
    r = validar_diagrama(d)
    assert any("'fantasma' não existe" in e for e in r["erros"])


def test_led_sem_resistor():
    d = diagrama([ESP, LED], [("esp:2", "led1:A"), ("led1:C", "esp:GND.1")])
    r = validar_diagrama(d)
    assert not r["valido"]
    assert any("sem resistor" in e for e in r["erros"])


def test_led_com_resistor_no_catodo_e_valido():
    d = diagrama([ESP, LED, R1], [("esp:2", "led1:A"), ("led1:C", "r1:1"), ("r1:2", "esp:GND.1")])
    assert validar_diagrama(d)["valido"]


def test_rgb_sem_resistor_em_uma_cor():
    rgb = ("rgb", "wokwi-rgb-led", {})
    r2 = ("r2", "wokwi-resistor", {})
    d = diagrama(
        [ESP, rgb, R1, r2],
        [
            ("esp:2", "r1:1"), ("r1:2", "rgb:R"),
            ("esp:4", "r2:1"), ("r2:2", "rgb:G"),
            ("esp:5", "rgb:B"),
            ("rgb:COM", "esp:GND.1"),
        ],
    )
    erros = validar_diagrama(d)["erros"]
    assert erros == ["LED 'rgb' (pino B) está sem resistor em série."]


def test_gnd_do_sensor_desligado():
    dht = ("dht", "wokwi-dht22", {})
    d = diagrama([ESP, dht], [("esp:3V3", "dht:VCC"), ("esp:15", "dht:SDA")])
    r = validar_diagrama(d)
    assert any("GND de 'dht'" in e for e in r["erros"])
    assert any("Nenhum pino GND da placa" in e for e in r["erros"])


def test_5v_direto_em_gpio_do_esp32():
    d = diagrama([ESP], [("esp:5V", "esp:4")])
    r = validar_diagrama(d)
    assert any("esp:5V (5 V) está ligado direto em esp:4" in e for e in r["erros"])


def test_potenciometro_em_3v3_e_valido_e_sem_avisos():
    pot = ("pot", "wokwi-potentiometer", {})
    d = diagrama([ESP, pot], [("esp:3V3", "pot:VCC"), ("pot:SIG", "esp:34"), ("pot:GND", "esp:GND.1")])
    assert validar_diagrama(d) == {"valido": True, "erros": [], "avisos": []}


def test_potenciometro_em_5v_avisa_no_sinal():
    pot = ("pot", "wokwi-potentiometer", {})
    d = diagrama([ESP, pot], [("esp:5V", "pot:VCC"), ("pot:SIG", "esp:34"), ("pot:GND", "esp:GND.1")])
    assert any("pino SIG vai direto em esp:34" in a for a in validar_diagrama(d)["avisos"])


def test_hc_sr04_em_5v_gera_aviso_no_echo():
    sr = ("sr", "wokwi-hc-sr04", {})
    d = diagrama(
        [ESP, sr],
        [("esp:5V", "sr:VCC"), ("sr:GND", "esp:GND.1"), ("esp:5", "sr:TRIG"), ("sr:ECHO", "esp:18")],
    )
    r = validar_diagrama(d)
    assert r["valido"]
    assert any("pino ECHO vai direto em esp:18" in a for a in r["avisos"])
    assert not any("TRIG" in a for a in r["avisos"])  # TRIG é entrada do sensor: 3,3 V basta


def test_tipo_desconhecido_vira_aviso():
    d = diagrama([ESP, ("x", "wokwi-peca-inventada", {})], [("esp:GND.1", "x:GND")])
    r = validar_diagrama(d)
    assert any("wokwi-peca-inventada" in a for a in r["avisos"])


# ---------- resistor_led ----------

def test_resistor_led_3v3_vermelho():
    r = resistor_led(3.3, 2.0, 10)
    assert r["resistor_ideal_ohms"] == 130.0
    assert r["resistor_comercial_ohms"] == 150.0
    assert r["corrente_real_ma"] == pytest.approx(8.67, abs=0.01)
    assert r["potencia_minima_resistor"] == "1/4 W"


def test_resistor_led_5v_valor_exato_da_serie():
    r = resistor_led(5.0, 2.0, 20)
    assert r["resistor_comercial_ohms"] == 150.0
    assert r["resistor_comercial"] == "150 Ω"


def test_resistor_led_entrada_invalida():
    assert "erro" in resistor_led(1.8, 2.0, 10)
    assert "erro" in resistor_led(5.0, 2.0, 0)


# ---------- divisor_tensao ----------

def test_divisor_5v_para_3v3():
    r = divisor_tensao(5.0, 3.3, 10000)
    assert r["r1_ideal_ohms"] == pytest.approx(5151.5, abs=0.1)
    assert r["r1_comercial_ohms"] == 5600.0
    assert r["r1_comercial"] == "5.6 kΩ"
    assert r["tensao_saida_real"] <= 3.3
    assert r["tensao_saida_real"] == pytest.approx(3.205, abs=0.001)


def test_divisor_saida_maior_que_entrada():
    assert "erro" in divisor_tensao(3.3, 5.0)


# ---------- largura_trilha ----------

def test_largura_trilha_1a_externa():
    # Valor de referência das calculadoras IPC-2221: ~11,8 mil (0,30 mm).
    r = largura_trilha(1.0, 1.0, 10)
    assert r["largura_mils"] == pytest.approx(11.8, abs=0.1)
    assert r["largura_mm"] == pytest.approx(0.30, abs=0.01)


def test_largura_trilha_interna_e_mais_larga():
    externa = largura_trilha(2.0)["largura_mm"]
    interna = largura_trilha(2.0, camada="interna")["largura_mm"]
    assert interna > 2 * externa


def test_largura_trilha_cobre_mais_grosso_e_mais_estreita():
    assert largura_trilha(1.0, 2.0)["largura_mm"] == pytest.approx(largura_trilha(1.0, 1.0)["largura_mm"] / 2, abs=0.001)


def test_largura_trilha_entrada_invalida():
    assert "erro" in largura_trilha(0)
    assert "erro" in largura_trilha(1, camada="meio")


# ---------- gerar_bom ----------

def test_bom_agrupa_pecas_iguais():
    d = diagrama(
        [ESP, LED, ("led2", "wokwi-led", {"color": "red"}), ("led3", "wokwi-led", {"color": "green"}),
         R1, ("r2", "wokwi-resistor", {"value": "220"}), ("r3", "wokwi-resistor", {})],
        [],
    )
    bom = gerar_bom(d)
    por_descricao = {i["descricao"]: i for i in bom["itens"]}
    assert bom["total_pecas"] == 7
    assert por_descricao["LED red"]["quantidade"] == 2
    assert por_descricao["LED red"]["referencias"] == ["led1", "led2"]
    assert por_descricao["Resistor 220 Ω"]["quantidade"] == 2
    assert por_descricao["Resistor 1 kΩ"]["quantidade"] == 1  # valor padrão do Wokwi
    assert por_descricao["Placa ESP32 DevKitC V4"]["quantidade"] == 1


# ---------- salvar_projeto ----------

def test_salvar_projeto_escreve_os_tres_arquivos(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    r = salvar_projeto("pisca", (EXEMPLO / "diagram.json").read_text(), "void setup(){}\nvoid loop(){}\n")
    pasta = tmp_path / "pisca"
    assert r["pasta"] == str(pasta)
    assert (pasta / "pisca.ino").read_text().startswith("void setup")
    assert json.loads((pasta / "diagram.json").read_text())["parts"][0]["id"] == "esp"
    toml = (pasta / "wokwi.toml").read_text()
    assert 'firmware = "build/pisca.ino.merged.bin"' in toml
    assert 'elf = "build/pisca.ino.elf"' in toml


def test_salvar_projeto_recusa_placa_que_nao_e_esp32(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    r = salvar_projeto("uno", diagrama([("uno", "wokwi-arduino-uno", {})], []), "")
    assert "só com ESP32" in r["erro"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("nome", ["../fora", "Com Espaco", "", "/abs", "a/b"])
def test_salvar_projeto_recusa_nome_perigoso(tmp_path, monkeypatch, nome):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    r = salvar_projeto(nome, (EXEMPLO / "diagram.json").read_text(), "")
    assert "erro" in r
    assert list(tmp_path.iterdir()) == []


def test_salvar_projeto_sem_placa(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    r = salvar_projeto("sem-placa", diagrama([LED], []), "")
    assert "Nenhuma placa suportada" in r["erro"]


def test_salvar_projeto_valida_antes_de_salvar(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    d = json.loads((EXEMPLO / "diagram.json").read_text())
    d["connections"] = [c for c in d["connections"] if not c[0].startswith("r1:2")]
    d["connections"].append(["esp:2", "led1:A", "green", []])  # LED sem resistor
    d["parts"] = [p for p in d["parts"] if p["id"] != "r1"]
    r = salvar_projeto("sem-resistor", json.dumps(d), "")
    assert "Corrija" in r["erro"] and r["erros"]
    assert list(tmp_path.iterdir()) == []


def test_salvar_projeto_remove_pontos_de_fio_invalidos(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    d = json.loads((EXEMPLO / "diagram.json").read_text())
    d["connections"][2][3] = ["-20us", "40mm", "h10", "v-5.5", "*"]
    salvar_projeto("fios", json.dumps(d), "")
    salvo = json.loads((tmp_path / "fios" / "diagram.json").read_text())
    assert salvo["connections"][2][3] == ["h10", "v-5.5", "*"]


# ---------- resumir_erros_compilacao ----------

SAIDA_GCC = """\
/home/u/projetos/x/x.ino: In function 'void loop()':
/home/u/projetos/x/x.ino:12:3: error: 'digitalWirte' was not declared in this scope; did you mean 'digitalWrite'?
   12 |   digitalWirte(2, HIGH);
      |   ^~~~~~~~~~~~
/home/u/projetos/x/x.ino:14:1: error: expected ';' before '}' token
/home/u/projetos/x/x.ino:12:3: error: 'digitalWirte' was not declared in this scope; did you mean 'digitalWrite'?
exit status 1

Compilation error: 'digitalWirte' was not declared in this scope; did you mean 'digitalWrite'?
"""


def test_resumir_erros_extrai_arquivo_linha_mensagem():
    r = resumir_erros_compilacao(SAIDA_GCC)
    assert r["total_erros"] == 2  # duplicado removido
    assert r["erros"][0] == {
        "arquivo": "x.ino",
        "linha": 12,
        "coluna": 3,
        "mensagem": "'digitalWirte' was not declared in this scope; did you mean 'digitalWrite'?",
    }
    assert r["erros"][1]["linha"] == 14


def test_resumir_erros_biblioteca_faltando_da_dica():
    saida = "/p/x/x.ino:1:10: fatal error: DHT.h: No such file or directory\ncompilation terminated.\n"
    r = resumir_erros_compilacao(saida)
    assert r["erros"][0]["mensagem"] == "DHT.h: No such file or directory"
    assert "arduino-cli lib install" in r["dica"]


def test_resumir_erros_sem_formato_gcc_devolve_ultimas_linhas():
    saida = "Error during build: Platform 'arduino:avr' not found: platform not installed\n"
    r = resumir_erros_compilacao(saida)
    assert r["erros"] == []
    assert r["saida"] == ["Error during build: Platform 'arduino:avr' not found: platform not installed"]
