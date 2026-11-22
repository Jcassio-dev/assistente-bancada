"""Pacote para continuar o projeto no wokwi.com.

O Wokwi não tem como abrir um projeto a partir de um link ou arquivo nosso, então
a bancada entrega os três arquivos que um projeto ESP32 do site usa, para colar
num projeto novo: sketch.ino, diagram.json e libraries.txt.
"""

import io
import re
import zipfile
from pathlib import Path

NOVO_PROJETO_ESP32 = "https://wokwi.com/projects/new/esp32"

# Cabeçalho incluído no sketch -> nome da biblioteca no gerenciador do Arduino/Wokwi.
BIBLIOTECAS = {
    "DHT.h": "DHT sensor library",
    "DHT_U.h": "DHT sensor library",
    "Adafruit_Sensor.h": "Adafruit Unified Sensor",
    "Adafruit_SSD1306.h": "Adafruit SSD1306",
    "Adafruit_GFX.h": "Adafruit GFX Library",
    "Adafruit_BusIO_Register.h": "Adafruit BusIO",
    "Adafruit_MPU6050.h": "Adafruit MPU6050",
    "ESP32Servo.h": "ESP32Servo",
    "LiquidCrystal_I2C.h": "LiquidCrystal I2C",
}


def bibliotecas_do_sketch(codigo):
    incluidos = re.findall(r'^\s*#include\s*[<"]([^>"]+)[>"]', codigo, flags=re.M)
    nomes = [BIBLIOTECAS[h] for h in incluidos if h in BIBLIOTECAS]
    if "DHT sensor library" in nomes:
        nomes.append("Adafruit Unified Sensor")  # dependência da biblioteca do DHT
    return list(dict.fromkeys(nomes))


def pacote_wokwi(pasta):
    """(nome do arquivo .zip, bytes) com sketch.ino, diagram.json e libraries.txt."""
    pasta = Path(pasta)
    sketch = next(pasta.glob("*.ino"), None)
    codigo = sketch.read_text(encoding="utf-8") if sketch else ""
    bibliotecas = bibliotecas_do_sketch(codigo)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("sketch.ino", codigo)
        z.writestr("diagram.json", (pasta / "diagram.json").read_text(encoding="utf-8"))
        z.writestr("libraries.txt", "# Bibliotecas do projeto (uma por linha)\n" + "\n".join(bibliotecas) + "\n")
    return f"{pasta.name}-wokwi.zip", memoria.getvalue()
