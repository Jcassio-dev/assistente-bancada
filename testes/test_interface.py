import json

import pytest

from interface import acompanhamento, conversas
from interface.acompanhamento import etapas_visiveis, registrar, rotulo, serial_sem_boot

EXEMPLO = json.loads(open("exemplos/teste-blink/diagram.json", encoding="utf-8").read())


@pytest.fixture
def projetos(tmp_path, monkeypatch):
    monkeypatch.setattr(acompanhamento, "PASTA_PROJETOS", tmp_path)

    def gravar(nome, diagrama):
        (tmp_path / nome).mkdir(exist_ok=True)
        (tmp_path / nome / "diagram.json").write_text(json.dumps(diagrama))

    return gravar


def test_rotulos_em_portugues():
    assert rotulo("buscar_documentos", {"documento": "dht22"}) == "Consultando o datasheet do DHT22"
    assert rotulo("buscar_documentos", {"documento": "wokwi-ssd1306"}) == "Consultando a referência do Wokwi (ssd1306)"
    assert rotulo("compilar", {"projeto": "x"}) == "Compilando o firmware"
    assert rotulo("ferramenta_nova", {}) == "Usando ferramenta_nova"


def test_salvar_define_projeto_e_etapas(projetos):
    projetos("pisca", EXEMPLO)
    conversa = conversas.nova()
    assert registrar(conversa, "salvar_projeto", {"nome": "pisca"}, json.dumps({"pasta": "/x/pisca"}))
    assert conversa["projeto"] == "pisca" and conversa["titulo"] == "pisca"
    assert conversa["etapas"] == {"validado": True} and conversa["destaques"] == []


def test_segundo_salvar_destaca_o_que_mudou(projetos):
    projetos("pisca", EXEMPLO)
    conversa = conversas.nova()
    registrar(conversa, "salvar_projeto", {"nome": "pisca"}, json.dumps({"pasta": "p"}))
    novo = json.loads(json.dumps(EXEMPLO))
    novo["connections"].append(["esp:5", "r1:1", "green", []])
    projetos("pisca", novo)
    registrar(conversa, "salvar_projeto", {"nome": "pisca"}, json.dumps({"pasta": "p"}))
    assert conversa["destaques"] == ["esp:5 | r1:1"]


def test_salvar_recusado_marca_erro(projetos):
    conversa = conversas.nova()
    registrar(conversa, "salvar_projeto", {"nome": "x"}, json.dumps({"erro": "O diagrama tem erros."}))
    assert conversa["projeto"] is None
    assert etapas_visiveis(conversa["etapas"]) == [("Ligações com erro", "erro")]


def test_etapas_de_compilacao_e_serial():
    conversa = conversas.nova()
    conversa["etapas"] = {"validado": True}
    uso = ["Sketch uses 308264 bytes (23%) of program storage space. Maximum is 1310720 bytes."]
    registrar(conversa, "compilar", {"projeto": "x"}, json.dumps({"sucesso": True, "uso_memoria": uso}))
    registrar(conversa, "wokwi_start_simulation", {}, "Simulation started successfully")
    registrar(conversa, "esperar_serial", {}, 'Texto "Temp" encontrado na serial.\n\nets...\nentry 0x400805b4\nTemp: 24\n')
    assert etapas_visiveis(conversa["etapas"]) == [
        ("Ligações conferidas", "ok"), ("Compilado, 23% da flash", "ok"), ("Simulado", "ok"), ("Serial confirmada", "ok")]
    assert conversa["serial"] == "Temp: 24"


def test_serial_sem_boot_quando_o_texto_nao_aparece():
    texto = 'O texto "X" NÃO apareceu na serial em 5 s. Não diga...\n\nSaída até agora:\nets Jul\nentry 0x40080\ninicio\n'
    assert serial_sem_boot(texto) == "inicio"


def test_conversas_salvar_listar_apagar(tmp_path, monkeypatch):
    monkeypatch.setattr(conversas, "PASTA", tmp_path)
    a, b = conversas.nova(), conversas.nova("termometro")
    conversas.salvar(a)
    conversas.salvar(b)
    assert [c["id"] for c in conversas.listar()] == [b["id"], a["id"]]
    assert conversas.carregar(b["id"])["projeto"] == "termometro"
    conversas.apagar(a["id"])
    assert [c["id"] for c in conversas.listar()] == [b["id"]]


def test_id_invalido_nao_vira_caminho(tmp_path, monkeypatch):
    monkeypatch.setattr(conversas, "PASTA", tmp_path)
    assert conversas.carregar("../../etc/passwd") is None
    with pytest.raises(ValueError):
        conversas.caminho("../x")


def test_titulo_do_pedido():
    assert conversas.titulo_do_pedido("Monte um LED") == "Monte um LED"
    assert conversas.titulo_do_pedido("x" * 60).endswith("...") and len(conversas.titulo_do_pedido("x" * 60)) == 42


def test_controles_e_leds_do_diagrama():
    from interface.simulacao import controles_do_diagrama, leds_do_diagrama

    diagrama = {"parts": [{"id": "esp", "type": "board-esp32-devkit-c-v4"}, {"id": "dht1", "type": "wokwi-dht22"},
                          {"id": "btn1", "type": "wokwi-pushbutton"}, {"id": "led1", "type": "wokwi-led"}]}
    controles = controles_do_diagrama(diagrama)
    assert [(i, t) for i, t, _ in controles] == [("dht1", "wokwi-dht22"), ("btn1", "wokwi-pushbutton")]
    assert [c[0] for c in controles[0][2]] == ["temperature", "humidity"]
    assert leds_do_diagrama(diagrama) == ["led1"]


def test_pacote_wokwi(tmp_path):
    import io
    import zipfile

    from interface.exportar import bibliotecas_do_sketch, pacote_wokwi

    (tmp_path / "termo.ino").write_text('#include <DHT.h>\n#include <Wire.h>\n#include "Adafruit_SSD1306.h"\n')
    (tmp_path / "diagram.json").write_text("{}")
    assert bibliotecas_do_sketch((tmp_path / "termo.ino").read_text()) == [
        "DHT sensor library", "Adafruit SSD1306", "Adafruit Unified Sensor"]
    nome, dados = pacote_wokwi(tmp_path)
    z = zipfile.ZipFile(io.BytesIO(dados))
    assert nome == f"{tmp_path.name}-wokwi.zip"
    assert sorted(z.namelist()) == ["diagram.json", "libraries.txt", "sketch.ino"]
    assert "DHT sensor library" in z.read("libraries.txt").decode()


def test_mover_peca_grava_posicao_e_rotacao(projetos):
    from interface.acompanhamento import mover_peca

    projetos("pisca", EXEMPLO)
    assert mover_peca("pisca", "led1", 310.4, -20, 90)
    salvo = acompanhamento.ler_diagrama("pisca")
    led = next(p for p in salvo["parts"] if p["id"] == "led1")
    assert (led["left"], led["top"], led["rotate"]) == (310, -20, 90)
    assert salvo["connections"] == EXEMPLO["connections"]
    assert mover_peca("pisca", "led1", 0, 0, 0) and "rotate" not in next(
        p for p in acompanhamento.ler_diagrama("pisca")["parts"] if p["id"] == "led1")
    assert not mover_peca("pisca", "nao-existe", 0, 0) and not mover_peca("outro", "led1", 0, 0)
