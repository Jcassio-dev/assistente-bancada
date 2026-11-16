---
name: circuito-para-placa
description: Levar um circuito com ESP32 que já funciona na simulação para uma placa de circuito impresso fabricável. Gera a lista de materiais, escolhe encapsulamentos, calcula a largura das trilhas, confere as regras da JLCPCB e as recomendações de hardware da Espressif e fecha com um checklist antes dos Gerbers. Use quando o usuário quiser fazer a placa, a PCB, a BOM ou mandar fabricar.
---

# Do circuito simulado para a placa

Ponto de partida: um `diagram.json` que passou no `validar_diagrama` e funcionou na simulação (skill `prototipar-circuito`). Se o diagrama não estiver na conversa, peça ao usuário ou proponha prototipar antes. Não desenhe a placa sem um circuito validado.

Esta skill não gera os Gerbers: ela prepara as decisões e o checklist para o usuário desenhar a placa no KiCad, EasyEDA ou similar.

## 1. Lista de materiais

Chame `gerar_bom(diagram_json)`. A BOM do Wokwi traz peças de simulação: complete com o que a placa real precisa e o simulador não mostra.
- **Placa ESP32:** a DevKitC inteira (mais simples, encaixe em barra de pinos) ou o módulo ESP32-WROOM-32 soldado direto na placa (menor, mas exige circuito de alimentação, reset e gravação). Pergunte ao usuário qual prefere se ele não disse; para um primeiro projeto, recomende a DevKitC.
- **Alimentação:** de onde vem a energia (USB da DevKitC, fonte externa, bateria) e o regulador de 3,3 V se usar o módulo.
- **Conectores:** barra de pinos ou borne para sensores externos e alimentação.
- **Desacoplamento:** capacitores perto da alimentação de cada CI.

## 2. Encapsulamentos

Para cada item da BOM, escolha PTH (furo passante) ou SMD e justifique em uma frase:
- PTH quando a montagem for manual por iniciante ou a peça sofrer esforço mecânico (conectores, botões, bornes).
- SMD quando o tamanho da placa importa ou a montagem for feita pelo fabricante. Prefira tamanhos fáceis de soldar à mão (0805 ou 1206) se o usuário for soldar.
- Sensores do Wokwi (DHT22, HC-SR04, SSD1306) costumam ser módulos prontos: use barra de pinos fêmea para encaixá-los.

## 3. Largura das trilhas

Estime a corrente de cada trilha de alimentação somando o consumo das peças ligadas nela. Busque o consumo nos datasheets com `buscar_documentos` (ex.: `buscar_documentos("current consumption Wi-Fi TX", documento="esp32-datasheet")`). Não invente correntes.

Chame `largura_trilha(corrente=..., espessura_cobre=1.0, elevacao_temperatura=10, camada="externa")` para cada trilha de alimentação, com margem (use pelo menos 1,5 vez a corrente estimada). Trilhas de sinal podem usar a largura padrão do projeto, desde que respeitem o mínimo do fabricante.

## 4. Regras do fabricante (JLCPCB)

Consulte as capacidades com `buscar_documentos(..., documento="jlcpcb")`, uma busca por item:
- largura mínima de trilha e espaçamento (`"min track width spacing 2 layer"`);
- diâmetro mínimo de furo e de via (`"min via hole size diameter"`);
- anel mínimo (`"annular ring"`);
- distância mínima entre cobre e borda da placa (`"copper to board edge"`).

Compare com os valores do passo 3: se a trilha calculada for menor que o mínimo do fabricante, use o mínimo do fabricante. Cite o documento em cada valor.

## 5. Recomendações da Espressif

Consulte o `esp32-hardware-design` (`buscar_documentos(..., documento="esp32-hardware-design")`) sobre:
- alimentação e capacitores de desacoplamento do ESP32 (`"power supply decoupling capacitor"`);
- strapping pins no boot (`"strapping pins"`), principalmente GPIO12, que define a tensão da flash e não pode ter pull-up externo;
- posição da antena: sem cobre e sem trilhas embaixo dela, e o módulo na borda da placa (`"antenna keepout area"`);
- circuito de reset (`"EN reset RC delay"`), se usar o módulo sem a DevKitC.

## 6. Checklist antes de gerar os Gerbers

Entregue ao usuário como lista marcável, com o valor e a fonte de cada item:

- [ ] Todas as ligações do `diagram.json` validado estão no esquemático, pino por pino.
- [ ] Trilhas de alimentação com a largura do passo 3 (ou o mínimo da JLCPCB, se for maior).
- [ ] Trilhas e espaçamentos de sinal acima do mínimo da JLCPCB.
- [ ] Furos e vias acima do mínimo da JLCPCB.
- [ ] Cobre afastado da borda pelo mínimo da JLCPCB.
- [ ] Capacitor de desacoplamento perto do pino de alimentação de cada CI.
- [ ] GPIO12 sem pull-up externo; GPIO0, GPIO2 e GPIO15 sem carga que mude o nível no boot.
- [ ] Nenhum sinal de 5 V ligado direto a um GPIO (divisor ou conversor de nível no lugar).
- [ ] Área da antena livre de cobre, com o módulo na borda da placa.
- [ ] Plano de GND contínuo, sem ilhas.
- [ ] Furos de fixação e legendas (silkscreen) com o nome de cada conector e o sentido de montagem.
- [ ] DRC do programa de desenho rodado com as regras da JLCPCB, sem erros.
- [ ] BOM final com encapsulamento de cada peça.
