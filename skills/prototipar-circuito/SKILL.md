---
name: prototipar-circuito
description: Montar e testar um circuito com ESP32 no simulador Wokwi a partir de um pedido do usuário. Consulta os datasheets, gera o diagram.json e o sketch, valida, compila, simula e confere a serial, corrigindo até funcionar. Use quando o usuário pedir para montar, ligar, testar ou simular um circuito.
---

# Prototipar um circuito com ESP32

O projeto trabalha só com ESP32: placa `board-esp32-devkit-c-v4` no Wokwi, FQBN `esp32:esp32:esp32`. Se o usuário pedir Arduino Uno, Nano, Pico ou outra placa, explique isso e ofereça o mesmo circuito no ESP32.

## 1. Entender o pedido

Antes de montar, tenha claro:
- quais peças entram (sensor, display, LED, botão, atuador) e o que o circuito deve fazer;
- o que deve aparecer na serial quando funcionar. Esse texto é o critério de sucesso da etapa 7.

Se faltar algo essencial (ex.: "um sensor de temperatura" sem dizer qual), escolha uma peça que existe no Wokwi (DHT22, NTC) e diga qual escolheu. Pergunte só se a escolha mudar muito o circuito.

Peças conhecidas pelo `validar_diagrama`: `wokwi-led`, `wokwi-rgb-led`, `wokwi-resistor`, `wokwi-pushbutton`, `wokwi-slide-switch`, `wokwi-buzzer`, `wokwi-potentiometer`, `wokwi-dht22`, `wokwi-hc-sr04`, `wokwi-servo`, `wokwi-photoresistor-sensor`, `wokwi-ntc-temperature-sensor`, `board-ssd1306`.

## 2. Consultar os datasheets

Use `buscar_documentos` para cada fato elétrico que for usar: tensão de alimentação do sensor, pinos, protocolo, endereço I2C, restrições de GPIO. Escreva a consulta em inglês com os termos do datasheet e use o filtro `documento` quando souber a fonte, por exemplo:
- `buscar_documentos("power supply voltage range", documento="dht22")`
- `buscar_documentos("input only GPIO34 GPIO39", documento="esp32-datasheet")`
- `buscar_documentos("default I2C address pins", documento="wokwi-ssd1306")`

Se os trechos não responderem, reformule (sinônimos, nome da tabela, outro documento) e busque de novo. Não use valores de tensão, corrente ou pino que não vieram de um trecho ou de uma ferramenta.

Restrições do ESP32 que valem sempre conferir:
- GPIOs trabalham em 3,3 V; 5 V direto num GPIO danifica o chip.
- GPIO34 a GPIO39 são só entrada (sem saída e sem pull-up interno).
- ADC2 não funciona com o Wi-Fi ligado; para leitura analógica prefira ADC1 (GPIO32 a GPIO39).
- GPIO0, GPIO2, GPIO12 e GPIO15 são strapping pins: evite carga que mude o nível deles no boot.

## 3. Montar o diagram.json e o código

`diagram.json` no formato do Wokwi:

```json
{
  "version": 1,
  "author": "Assistente de Bancada",
  "editor": "wokwi",
  "parts": [
    { "type": "board-esp32-devkit-c-v4", "id": "esp", "top": 0, "left": 0, "attrs": {} },
    { "type": "wokwi-resistor", "id": "r1", "top": 80, "left": 150, "rotate": 90, "attrs": { "value": "220" } },
    { "type": "wokwi-led", "id": "led1", "top": 0, "left": 180, "attrs": { "color": "red" } }
  ],
  "connections": [
    [ "esp:TX", "$serialMonitor:RX", "", [] ],
    [ "esp:RX", "$serialMonitor:TX", "", [] ],
    [ "esp:2", "r1:1", "green", [] ],
    [ "r1:2", "led1:A", "green", [] ],
    [ "led1:C", "esp:GND.2", "black", [] ]
  ],
  "dependencies": {}
}
```

Regras:
- Sempre ligue `esp:TX` e `esp:RX` ao `$serialMonitor`, senão a serial não aparece na simulação.
- Pinos do ESP32 DevKitC no Wokwi: números (`2`, `4`, `5`, `12` a `19`, `21` a `23`, `25` a `27`, `32` a `35`), `3V3`, `5V`, `GND.1`, `GND.2`, `GND.3`, `VP`, `VN`, `EN`, `TX`, `RX`.
- Sensores que aceitam 3,3 V devem ser alimentados no `3V3`.
- Todo LED leva resistor em série. Calcule com `resistor_led(tensao_fonte=3.3, tensao_led=..., corrente_ma=...)`.
- Para baixar um sinal de 5 V para o GPIO, use `divisor_tensao`.

Código (sketch Arduino para o core esp32):
- `Serial.begin(115200)` no `setup()` e uma mensagem inicial fixa (ex.: `"termometro iniciado"`).
- Escreva na serial o que o circuito mede ou faz, com texto previsível, para a etapa 7 conferir.
- Bibliotecas comuns: `DHT sensor library` (DHT22), `Adafruit SSD1306` e `Adafruit GFX Library` (OLED), `ESP32Servo` (servo).

## 4. Validar

Chame `validar_diagrama(diagram_json)`. Corrija **todos** os `erros` e valide de novo até `valido` ser verdadeiro. Leia os `avisos` e corrija os que fazem sentido (ex.: sinal de sensor em 5 V indo direto para um GPIO). Só siga quando a validação passar.

## 5. Salvar e compilar

1. `salvar_projeto(nome, diagram_json, codigo)`, com nome em minúsculas, sem espaços (ex.: `termometro-dht22`). Guarde a `pasta` devolvida.
2. `compilar(projeto=nome)`.
3. Se `sucesso` for falso, leia `erros` (arquivo, linha, mensagem), corrija o código, salve de novo e compile de novo. Se vier `dica` de biblioteca faltando, diga ao usuário qual biblioteca instalar com `arduino-cli lib install "<nome>"` ou troque por código sem a biblioteca.
4. Pare depois de 3 tentativas sem sucesso e explique ao usuário o erro que sobrou.

## 6. Simular

`wokwi_start_simulation(projectPath=<pasta devolvida pelo salvar_projeto>)`.

Para circuitos com entrada do usuário, use `wokwi_set_control(partId, control, value)` (ex.: mudar a temperatura do DHT22 ou girar o potenciômetro) e `wokwi_read_pin(partId, pin)` para conferir uma saída.

## 7. Ler a serial e conferir

Chame `wokwi_read_serial()` e compare com o que foi definido na etapa 1.
- Se a serial estiver vazia, espere e leia de novo (o boot do ESP32 leva cerca de 1 s simulado).
- Se o texto não bater (leitura `nan` do sensor, valor fora da faixa, mensagem errada), descubra a causa (pino trocado no código ou no diagrama, alimentação, biblioteca), corrija, volte à etapa 4 e simule de novo.
- Termine com `wokwi_stop_simulation()`.

## 8. Responder ao usuário

Mostre:
- a lista de ligações em texto (ex.: "DHT22 VCC no 3V3, SDA no GPIO15, GND no GND.1");
- o código final;
- o trecho da serial que comprova o funcionamento;
- os documentos e páginas consultados para cada valor elétrico usado;
- a pasta do projeto, para abrir no Wokwi.
