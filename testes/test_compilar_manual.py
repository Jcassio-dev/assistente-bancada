"""Testes manuais: compilam de verdade com o arduino-cli (demoram).

Rodar com:  pytest -m manual -s
"""

import shutil
from pathlib import Path

import pytest

from servidor_bancada import servidor
from servidor_bancada.servidor import compilar, salvar_projeto

EXEMPLO = Path(__file__).resolve().parent.parent / "exemplos" / "teste-blink"

pytestmark = [
    pytest.mark.manual,
    pytest.mark.skipif(shutil.which("arduino-cli") is None, reason="arduino-cli não instalado"),
]


def test_compilar_teste_blink():
    # Mesmo caminho do agente: salvar_projeto cria projetos/teste-blink e compilar gera o firmware.
    salvo = salvar_projeto(
        "teste-blink",
        (EXEMPLO / "diagram.json").read_text(),
        (EXEMPLO / "teste-blink.ino").read_text(),
    )
    assert "erro" not in salvo, salvo

    r = compilar("teste-blink")
    print(r)
    assert r["sucesso"], r
    assert r["fqbn"] == "esp32:esp32:esp32"
    assert Path(r["firmware"]).exists()
    assert Path(salvo["pasta"], "build", "teste-blink.ino.elf").exists()


def test_compilar_codigo_com_erro_devolve_linha(tmp_path, monkeypatch):
    monkeypatch.setattr(servidor, "PASTA_PROJETOS", tmp_path)
    codigo = (EXEMPLO / "teste-blink.ino").read_text().replace("digitalWrite", "digitalWirte")
    salvar_projeto("quebrado", (EXEMPLO / "diagram.json").read_text(), codigo)

    r = compilar("quebrado")
    print(r)
    assert not r["sucesso"]
    assert r["erros"][0]["arquivo"] == "quebrado.ino"
    assert r["erros"][0]["linha"] == 13
    assert "digitalWirte" in r["erros"][0]["mensagem"]


def test_compilar_projeto_inexistente():
    assert "não encontrado" in compilar("nao-existe-esse-projeto")["erro"]
