"""Painel "Bancada" da interface: desenha o circuito do projeto atual ao lado do chat.

As peças vêm da biblioteca @wokwi/elements (MIT) e as placas (ESP32 DevKitC V4,
display SSD1306) dos desenhos do repositório wokwi-boards. Os dois são carregados
por CDN, em versão fixa, e não ficam no nosso repositório. Os fios são traçados
entre as coordenadas dos pinos. As imagens capturadas por capturar_display são
desenhadas na tela do display.
"""

import base64
import json
from pathlib import Path

VERSAO_ELEMENTOS = "1.9.2"
COMMIT_PLACAS = "962b19d5636756537a93bb5337ac99abd775eae0"


def chave_conexao(c):
    """Identifica uma ligação sem depender da ordem das pontas."""
    return " | ".join(sorted([c[0], c[1]]))


def ligacoes(diagrama):
    """Ligações entre peças (sem o monitor serial), como pares (de, para, cor)."""
    return [
        (c[0], c[1], c[2] if len(c) > 2 else "")
        for c in diagrama.get("connections", [])
        if not c[0].startswith("$") and not c[1].startswith("$")
    ]


def novidades(diagrama, anterior):
    """Peças e ligações que não existiam na versão anterior do diagrama."""
    if not anterior:
        return set()
    pecas = {p["id"] for p in anterior.get("parts", [])}
    conexoes = {chave_conexao(c) for c in anterior.get("connections", [])}
    novas = {p["id"] for p in diagrama.get("parts", []) if p["id"] not in pecas}
    novas |= {chave_conexao(c) for c in diagrama.get("connections", []) if chave_conexao(c) not in conexoes}
    return novas


def telas_atualizadas(pasta):
    """{id da peça: PNG em base64} das capturas mais novas que o diagrama e o código."""
    pasta = Path(pasta)
    referencia = max((f.stat().st_mtime for f in [pasta / "diagram.json", *pasta.glob("*.ino")] if f.exists()), default=0)
    return {
        png.stem: base64.b64encode(png.read_bytes()).decode()
        for png in sorted((pasta / "telas").glob("*.png"))
        if png.stat().st_mtime >= referencia
    }


def html_bancada(diagrama, telas=None, destaques=None, altura=460):
    dados = json.dumps(
        {"diagrama": diagrama, "telas": telas or {}, "destaques": sorted(destaques or [])},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return (
        MODELO_HTML.replace("__DADOS__", dados)
        .replace("__ALTURA__", str(altura))
        .replace("__VERSAO__", VERSAO_ELEMENTOS)
        .replace("__COMMIT__", COMMIT_PLACAS)
    )


MODELO_HTML = r"""<!doctype html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/@wokwi/elements@__VERSAO__/dist/wokwi-elements.bundle.js"></script>
<style>
  html, body { margin: 0; background: #f4f1ea; font-family: system-ui, sans-serif; }
  #area { position: relative; width: 100%; height: __ALTURA__px; overflow: hidden; }
  #mesa { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
  .peca { position: absolute; }
  .peca img { display: block; }
  .tela { position: absolute; image-rendering: pixelated; }
  .rotulo { position: absolute; font-size: 11px; color: #555; white-space: nowrap; }
  .desconhecida { border: 1px dashed #999; padding: 6px; font-size: 11px; background: #fff; }
  .nova { outline: 2px solid #f0a020; outline-offset: 3px; border-radius: 4px; }
  svg#fios { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
  svg#fios path { fill: none; stroke-linecap: round; stroke-linejoin: round; pointer-events: stroke; }
  #aviso { position: absolute; bottom: 4px; left: 8px; font-size: 11px; color: #a33; }
</style></head>
<body><div id="area"><div id="mesa"><svg id="fios"></svg></div><div id="aviso"></div></div>
<script>
const DADOS = __DADOS__;
const MM = 3.7795;  // pixels por milímetro (mesma escala do Wokwi)
const PLACAS = "https://cdn.jsdelivr.net/gh/wokwi/wokwi-boards@__COMMIT__/boards/";
const CORES = { green: "#2e8b57", red: "#d22", black: "#222", blue: "#2266dd", yellow: "#d4a017",
                orange: "#ee7700", white: "#bbb", purple: "#8a2be2", gray: "#888", grey: "#888", "": "#2e8b57" };
const mesa = document.getElementById("mesa");
const destaques = new Set(DADOS.destaques);

async function lerPlaca(nome) {
  const texto = await (await fetch(PLACAS + nome + "/board.json")).text();
  return JSON.parse(texto.replace(/\/\*[\s\S]*?\*\//g, ""));  // board.json tem comentários
}

async function montarPeca(parte) {
  const caixa = document.createElement("div");
  caixa.className = "peca" + (destaques.has(parte.id) ? " nova" : "");
  caixa.style.left = (parte.left || 0) + "px";
  caixa.style.top = (parte.top || 0) + "px";
  caixa.title = parte.id + " (" + parte.type + ")";
  mesa.appendChild(caixa);
  let pinos = {};

  if (parte.type.startsWith("board-")) {
    const nome = parte.type.slice(6);
    const placa = await lerPlaca(nome);
    const img = document.createElement("img");
    img.src = PLACAS + nome + "/board.svg";
    img.style.width = placa.width * MM + "px";
    img.style.height = placa.height * MM + "px";
    caixa.appendChild(img);
    for (const [p, info] of Object.entries(placa.pins)) pinos[p] = { x: info.x * MM, y: info.y * MM };
    const tela = DADOS.telas[parte.id];
    if (tela && placa.displays && placa.displays.length) {
      const d = placa.displays[0];
      const t = document.createElement("img");
      t.className = "tela";
      t.src = "data:image/png;base64," + tela;
      Object.assign(t.style, { left: d.x * MM + "px", top: d.y * MM + "px", width: d.width * MM + "px", height: d.height * MM + "px" });
      caixa.appendChild(t);
    }
  } else if (customElements.get(parte.type)) {
    const el = document.createElement(parte.type);
    for (const [k, v] of Object.entries(parte.attrs || {})) el.setAttribute(k, v);
    caixa.appendChild(el);
    await el.updateComplete;
    for (const p of el.pinInfo || []) pinos[p.name] = { x: p.x, y: p.y };
  } else {
    caixa.innerHTML = '<div class="desconhecida">' + parte.id + "<br>" + parte.type + "</div>";
  }

  const rotulo = document.createElement("div");
  rotulo.className = "rotulo";
  rotulo.textContent = parte.id;
  caixa.appendChild(rotulo);
  return { caixa, pinos, rotacao: parte.rotate || 0 };
}

function posicaoPino(peca, nome) {
  const pino = peca.pinos[nome];
  if (!pino) return null;
  const w = peca.caixa.offsetWidth, h = peca.caixa.offsetHeight;
  const ang = (peca.rotacao * Math.PI) / 180;
  const dx = pino.x - w / 2, dy = pino.y - h / 2;
  return {
    x: peca.caixa.offsetLeft + w / 2 + dx * Math.cos(ang) - dy * Math.sin(ang),
    y: peca.caixa.offsetTop + h / 2 + dx * Math.sin(ang) + dy * Math.cos(ang),
  };
}

async function desenhar() {
  const pecas = {};
  for (const parte of DADOS.diagrama.parts || []) {
    pecas[parte.id] = await montarPeca(parte);
    if (pecas[parte.id].rotacao) pecas[parte.id].caixa.style.transform = "rotate(" + pecas[parte.id].rotacao + "deg)";
  }
  await new Promise((r) => setTimeout(r, 150));  // espera as imagens das placas definirem o tamanho

  const svg = document.getElementById("fios");
  const faltando = [];
  const pontos = [];
  for (const c of DADOS.diagrama.connections || []) {
    const [de, para, cor] = c;
    if (de.startsWith("$") || para.startsWith("$")) continue;
    const [pa, pinoA] = [de.slice(0, de.indexOf(":")), de.slice(de.indexOf(":") + 1)];
    const [pb, pinoB] = [para.slice(0, para.indexOf(":")), para.slice(para.indexOf(":") + 1)];
    const a = pecas[pa] && posicaoPino(pecas[pa], pinoA);
    const b = pecas[pb] && posicaoPino(pecas[pb], pinoB);
    if (!a || !b) { faltando.push(de + " / " + para); continue; }
    pontos.push(a, b);
    const meio = (a.y + b.y) / 2;
    const caminho = document.createElementNS("http://www.w3.org/2000/svg", "path");
    caminho.setAttribute("d", `M ${a.x} ${a.y} V ${meio} H ${b.x} V ${b.y}`);
    const nova = destaques.has([de, para].sort().join(" | "));
    caminho.setAttribute("stroke", CORES[cor] || cor || CORES[""]);
    caminho.setAttribute("stroke-width", nova ? 4 : 2.2);
    if (nova) caminho.setAttribute("stroke-dasharray", "8 4");
    const titulo = document.createElementNS("http://www.w3.org/2000/svg", "title");
    titulo.textContent = de + " ligado em " + para + (nova ? " (nova)" : "");
    caminho.appendChild(titulo);
    svg.appendChild(caminho);
  }

  // enquadra tudo na área visível
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of Object.values(pecas)) {
    const r = p.caixa.getBoundingClientRect(), m = mesa.getBoundingClientRect();
    x0 = Math.min(x0, r.left - m.left); y0 = Math.min(y0, r.top - m.top);
    x1 = Math.max(x1, r.right - m.left); y1 = Math.max(y1, r.bottom - m.top + 14);
  }
  for (const p of pontos) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
  const area = document.getElementById("area");
  const margem = 20;
  const escala = Math.min((area.clientWidth - 2 * margem) / (x1 - x0), (area.clientHeight - 2 * margem) / (y1 - y0), 2.5);
  const sobraX = (area.clientWidth - (x1 - x0) * escala) / 2, sobraY = (area.clientHeight - (y1 - y0) * escala) / 2;
  mesa.style.transform = `translate(${sobraX - x0 * escala}px, ${sobraY - y0 * escala}px) scale(${escala})`;
  if (faltando.length) document.getElementById("aviso").textContent = "Pinos não encontrados no desenho: " + faltando.join(", ");
}

customElements.whenDefined("wokwi-led").then(desenhar).catch((e) => {
  document.getElementById("aviso").textContent = "Não foi possível desenhar a bancada: " + e;
});
</script></body></html>"""
