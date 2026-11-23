"""Mesa da bancada (componente Streamlit v2).

Eventos para o Python: mover {id, left, top, rotate}, controle {parte, controle, valor}
e botao {parte}.
"""

import streamlit as st

from interface.painel import COMMIT_PLACAS, VERSAO_ELEMENTOS

CSS = """
.bancada { font-family: "Source Sans 3", system-ui, sans-serif; color: #e4e7e5; }
.area { position: relative; width: 100%; height: var(--altura, 480px); overflow: hidden; border-radius: 10px;
        background-color: #1b2b25;
        background-image: linear-gradient(rgba(255,255,255,.045) 1px, transparent 1px),
                          linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px);
        background-size: 24px 24px; user-select: none; }
.mesa { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.peca { position: absolute; cursor: grab; touch-action: none; }
.peca.arrastando { cursor: grabbing; filter: drop-shadow(0 6px 10px rgba(0,0,0,.5)); z-index: 5; }
.peca img { display: block; pointer-events: none; }
.tela { position: absolute; image-rendering: pixelated; pointer-events: none; }
.rotulo { position: absolute; font-size: 10px; line-height: 1; color: #b4cbbf; background: rgba(20,32,28,.78);
          padding: 2px 4px; border-radius: 3px; white-space: nowrap; font-family: ui-monospace, monospace;
          pointer-events: none; z-index: 4; }
.desconhecida { border: 1px dashed #999; padding: 6px; font-size: 11px; background: #fff; color: #222; }
.nova { outline: 2px dashed #e8a33d; outline-offset: 4px; border-radius: 4px; }
svg.fios { position: absolute; left: 0; top: 0; overflow: visible; pointer-events: none; }
svg.fios path { fill: none; stroke-linecap: round; stroke-linejoin: round; }
.vazia { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
         justify-content: center; color: #8fa89c; text-align: center; padding: 0 40px; }
.vazia b { color: #cfe3d8; font-size: 15px; margin-bottom: 6px; font-weight: 600; }
.vazia span { font-size: 13px; line-height: 1.5; }
.dica { position: absolute; right: 10px; bottom: 8px; font-size: 11px; color: #7f998c; pointer-events: none; }
.aviso { position: absolute; left: 10px; bottom: 8px; font-size: 11px; color: #f08a7a; }
.aovivo { margin-top: 10px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
.aovivo[hidden] { display: none; }
.cartao { background: #1c2224; border: 1px solid #2c3437; border-radius: 10px; padding: 10px 12px; }
.cartao h4 { margin: 0 0 8px 0; font-size: 13px; font-weight: 600; color: #cfd6d2; }
.status { grid-column: 1 / -1; font-size: 13px; color: #86d9a6; display: flex; align-items: center; gap: 8px; }
.status::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #3cb371;
                  box-shadow: 0 0 6px #3cb371; animation: pulsar 1.2s infinite; }
.status.iniciando { color: #e8a33d; }
.status.iniciando::before { background: #e8a33d; box-shadow: 0 0 6px #e8a33d; }
@keyframes pulsar { 50% { opacity: .35; } }
.controle { margin-bottom: 10px; }
.controle label { display: flex; justify-content: space-between; font-size: 12px; color: #b9c2bd; margin-bottom: 2px; }
.controle label b { color: #e8a33d; font-weight: 600; font-variant-numeric: tabular-nums; }
.controle input { width: 100%; accent-color: #e8a33d; }
.botao { background: #2a3134; color: #e4e7e5; border: 1px solid #3a4447; border-radius: 8px; padding: 6px 12px;
         cursor: pointer; font-size: 13px; }
.botao:active { background: #e8a33d; color: #131718; }
pre.serial { margin: 0; height: 150px; overflow: auto; font-size: 12px; line-height: 1.45; color: #cfe3d8;
             font-family: ui-monospace, monospace; white-space: pre-wrap; }
.sem-controles { font-size: 12px; color: #7f998c; }
"""

HTML = """
<div class="bancada">
  <div class="area">
    <div class="mesa"><svg class="fios"></svg></div>
    <div class="aviso"></div>
    <div class="dica"></div>
  </div>
  <div class="aovivo" hidden>
    <div class="status"></div>
    <div class="cartao"><h4>Controles</h4><div class="controles"></div></div>
    <div class="cartao"><h4>Serial</h4><pre class="serial"></pre></div>
  </div>
</div>
"""

JS = r"""
const BIBLIOTECA = "https://cdn.jsdelivr.net/npm/@wokwi/elements@__VERSAO__/dist/wokwi-elements.bundle.js";
const PLACAS = "https://cdn.jsdelivr.net/gh/wokwi/wokwi-boards@__COMMIT__/boards/";
const MM = 3.7795;  // pixels por milímetro (mesma escala do Wokwi)
const CORES = { green: "#3cb371", red: "#e53935", black: "#111", blue: "#3f7fe8", yellow: "#e0b326",
                orange: "#f08a24", white: "#eee", purple: "#9b59d0", gray: "#999", grey: "#999", "": "#3cb371" };
const SVG = "http://www.w3.org/2000/svg";

function carregarBiblioteca() {
  if (!window.__elementosWokwi) {
    window.__elementosWokwi = new Promise((ok, erro) => {
      const s = document.createElement("script");
      s.src = BIBLIOTECA; s.onload = ok; s.onerror = erro;
      document.head.appendChild(s);
    }).then(() => customElements.whenDefined("wokwi-led"));
  }
  return window.__elementosWokwi;
}

const placas = (window.__placasWokwi = window.__placasWokwi || {});
function lerPlaca(nome) {
  if (!placas[nome]) {
    // board.json tem comentários /* */, que o JSON.parse não aceita
    placas[nome] = fetch(PLACAS + nome + "/board.json").then((r) => r.text())
      .then((t) => JSON.parse(t.replace(/\/\*[\s\S]*?\*\//g, "")));
  }
  return placas[nome];
}

function estrutura(raiz) {
  const q = (s) => raiz.querySelector(s);
  return { area: q(".area"), mesa: q(".mesa"), svg: q("svg.fios"), aviso: q(".aviso"), dica: q(".dica"),
           aovivo: q(".aovivo"), status: q(".status"), controles: q(".controles"), serial: q("pre.serial"),
           pecas: {}, escala: 1, versao: 0 };
}

async function montarPeca(b, parte) {
  const caixa = document.createElement("div");
  caixa.className = "peca" + (b.destaques.has(parte.id) ? " nova" : "");
  caixa.style.left = (parte.left || 0) + "px";
  caixa.style.top = (parte.top || 0) + "px";
  caixa.title = parte.id + " (" + parte.type + "). Arraste para mover, duplo clique para girar.";
  b.mesa.appendChild(caixa);
  const peca = { parte, caixa, pinos: {}, rotacao: parte.rotate || 0, elemento: null };

  if (parte.type.startsWith("board-")) {
    const nome = parte.type.slice(6);
    const placa = await lerPlaca(nome);
    const img = document.createElement("img");
    img.src = PLACAS + nome + "/board.svg";
    img.style.width = placa.width * MM + "px";
    img.style.height = placa.height * MM + "px";
    img.draggable = false;
    caixa.appendChild(img);
    for (const [p, info] of Object.entries(placa.pins)) peca.pinos[p] = { x: info.x * MM, y: info.y * MM };
    const tela = b.telas[parte.id];
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
    for (const p of el.pinInfo || []) peca.pinos[p.name] = { x: p.x, y: p.y };
    peca.elemento = el;
  } else {
    caixa.innerHTML = '<div class="desconhecida">' + parte.id + "<br>" + parte.type + "</div>";
  }
  // o rótulo fica fora da peça para não girar junto; desenharFios o posiciona
  peca.rotulo = document.createElement("div");
  peca.rotulo.className = "rotulo";
  peca.rotulo.textContent = parte.id;
  b.mesa.appendChild(peca.rotulo);
  if (peca.rotacao) caixa.style.transform = "rotate(" + peca.rotacao + "deg)";
  arrastavel(b, peca);
  return peca;
}

function posicaoPino(peca, nome) {
  const pino = peca.pinos[nome];
  if (!pino) return null;
  const w = peca.caixa.offsetWidth, h = peca.caixa.offsetHeight;
  const ang = (peca.rotacao * Math.PI) / 180;
  const dx = pino.x - w / 2, dy = pino.y - h / 2;
  let saida = (pino.x < 0.2 * w || pino.x > 0.8 * w) && pino.y > 0.08 * h && pino.y < 0.92 * h ? "h" : "v";
  if (Math.round(peca.rotacao / 90) % 2) saida = saida === "h" ? "v" : "h";
  return { x: peca.caixa.offsetLeft + w / 2 + dx * Math.cos(ang) - dy * Math.sin(ang),
           y: peca.caixa.offsetTop + h / 2 + dx * Math.sin(ang) + dy * Math.cos(ang), saida };
}

function contorno(p) {
  const w = p.caixa.offsetWidth, h = p.caixa.offsetHeight;
  const [bw, bh] = Math.round(p.rotacao / 90) % 2 ? [h, w] : [w, h];
  const cx = p.caixa.offsetLeft + w / 2, cy = p.caixa.offsetTop + h / 2;
  return { x0: cx - bw / 2, y0: cy - bh / 2, x1: cx + bw / 2, y1: cy + bh / 2 };
}

function desembaracar(b) {
  const pecas = Object.values(b.pecas);
  const folga = 10, movidas = [];
  const livre = (p, c) => pecas.every((q) => {
    if (q === p) return true;
    const o = contorno(q);
    return c.x1 + folga <= o.x0 || c.x0 >= o.x1 + folga || c.y1 + folga <= o.y0 || c.y0 >= o.y1 + folga;
  });
  for (const p of pecas) {
    if (p.parte.type.startsWith("board-")) continue;
    const c = contorno(p);
    if (livre(p, c)) continue;
    let melhor = null;
    for (let d = 10; d <= 400 && !melhor; d += 10) {
      for (const [dx, dy] of [[-d, 0], [d, 0], [0, d], [0, -d]]) {
        if (livre(p, { x0: c.x0 + dx, x1: c.x1 + dx, y0: c.y0 + dy, y1: c.y1 + dy })) { melhor = [dx, dy]; break; }
      }
    }
    if (!melhor) continue;
    p.parte.left = Math.round((p.parte.left || 0) + melhor[0]);
    p.parte.top = Math.round((p.parte.top || 0) + melhor[1]);
    p.caixa.style.left = p.parte.left + "px";
    p.caixa.style.top = p.parte.top + "px";
    movidas.push({ id: p.parte.id, left: p.parte.left, top: p.parte.top, rotate: p.rotacao });
  }
  return movidas;
}

function posicionarRotulos(b) {
  const pecas = Object.values(b.pecas);
  const caixas = new Map(pecas.map((p) => [p, contorno(p)]));
  const bate = (r, dono) => pecas.some((q) => {
    if (q === dono) return false;
    const c = caixas.get(q);
    return r.x0 < c.x1 && r.x1 > c.x0 && r.y0 < c.y1 && r.y1 > c.y0;
  });
  for (const p of pecas) {
    if (!p.rotulo) continue;
    const c = caixas.get(p), lw = p.rotulo.offsetWidth, lh = p.rotulo.offsetHeight;
    const opcoes = [[c.x0, c.y1 + 4], [c.x1 + 4, (c.y0 + c.y1 - lh) / 2],
                    [c.x0 - lw - 4, (c.y0 + c.y1 - lh) / 2], [c.x0, c.y0 - lh - 4]];
    const [x, y] = opcoes.find(([x, y]) => !bate({ x0: x, y0: y, x1: x + lw, y1: y + lh }, p)) || opcoes[0];
    p.rotulo.style.left = x + "px";
    p.rotulo.style.top = y + "px";
  }
}

function desenharFios(b) {
  posicionarRotulos(b);
  b.svg.replaceChildren();
  const faltando = [];
  const pontos = [];
  for (const [de, para, cor] of b.diagrama.connections || []) {
    if (de.startsWith("$") || para.startsWith("$")) continue;
    const [pa, pinoA] = [de.slice(0, de.indexOf(":")), de.slice(de.indexOf(":") + 1)];
    const [pb, pinoB] = [para.slice(0, para.indexOf(":")), para.slice(para.indexOf(":") + 1)];
    const a = b.pecas[pa] && posicaoPino(b.pecas[pa], pinoA);
    const z = b.pecas[pb] && posicaoPino(b.pecas[pb], pinoB);
    if (!a || !z) { faltando.push(de + " / " + para); continue; }
    pontos.push(a, z);
    let d;
    if (a.saida === "h" && z.saida === "h") d = `M ${a.x} ${a.y} H ${(a.x + z.x) / 2} V ${z.y} H ${z.x}`;
    else if (a.saida === "v" && z.saida === "v") d = `M ${a.x} ${a.y} V ${(a.y + z.y) / 2} H ${z.x} V ${z.y}`;
    else if (a.saida === "h") d = `M ${a.x} ${a.y} H ${z.x} V ${z.y}`;
    else d = `M ${a.x} ${a.y} V ${z.y} H ${z.x}`;
    const nova = b.destaques.has([de, para].sort().join(" | "));
    const tinta = CORES[cor] || cor || CORES[""];
    for (const [stroke, largura] of [[nova ? "rgba(232,163,61,.55)" : "rgba(255,255,255,.28)", nova ? 7 : 4.2],
                                     [tinta, nova ? 3.2 : 2.2]]) {
      const p = document.createElementNS(SVG, "path");
      p.setAttribute("d", d); p.setAttribute("stroke", stroke); p.setAttribute("stroke-width", largura);
      b.svg.appendChild(p);
    }
    for (const ponta of [a, z]) {
      const c = document.createElementNS(SVG, "circle");
      for (const [k, v] of Object.entries({ cx: ponta.x, cy: ponta.y, r: 2.6, fill: tinta,
                                             stroke: "rgba(255,255,255,.6)", "stroke-width": 1 })) c.setAttribute(k, v);
      b.svg.appendChild(c);
    }
  }
  b.aviso.textContent = faltando.length ? "Pinos não encontrados no desenho: " + faltando.join(", ") : "";
  return pontos;
}

function enquadrar(b, pontos) {
  b.mesa.style.transform = "none";
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const m = b.mesa.getBoundingClientRect();
  for (const p of Object.values(b.pecas)) {
    const r = p.caixa.getBoundingClientRect();
    x0 = Math.min(x0, r.left - m.left); y0 = Math.min(y0, r.top - m.top);
    x1 = Math.max(x1, r.right - m.left); y1 = Math.max(y1, r.bottom - m.top + 14);
  }
  for (const p of pontos) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); }
  const margem = 28, W = b.area.clientWidth, H = b.area.clientHeight;
  b.escala = Math.min((W - 2 * margem) / (x1 - x0), (H - 2 * margem) / (y1 - y0), 1.6);
  const tx = (W - (x1 - x0) * b.escala) / 2 - x0 * b.escala, ty = (H - (y1 - y0) * b.escala) / 2 - y0 * b.escala;
  b.mesa.style.transform = `translate(${tx}px, ${ty}px) scale(${b.escala})`;
}

function foraDaArea(b) {
  const a = b.area.getBoundingClientRect();
  return Object.values(b.pecas).some((p) => {
    const r = p.caixa.getBoundingClientRect();
    return r.left < a.left || r.top < a.top || r.right > a.right || r.bottom > a.bottom;
  });
}

function arrastavel(b, peca) {
  const { caixa, parte } = peca;
  caixa.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !b.editavel) return;
    e.preventDefault();
    caixa.setPointerCapture(e.pointerId);
    const inicio = { x: e.clientX, y: e.clientY, left: parte.left || 0, top: parte.top || 0 };
    let moveu = false;
    const mover = (ev) => {
      const dx = (ev.clientX - inicio.x) / b.escala, dy = (ev.clientY - inicio.y) / b.escala;
      if (!moveu && Math.abs(dx) + Math.abs(dy) < 3) return;
      moveu = true;
      caixa.classList.add("arrastando");
      parte.left = Math.round(inicio.left + dx);
      parte.top = Math.round(inicio.top + dy);
      caixa.style.left = parte.left + "px";
      caixa.style.top = parte.top + "px";
      desenharFios(b);
    };
    const soltar = () => {
      caixa.removeEventListener("pointermove", mover);
      caixa.classList.remove("arrastando");
      if (!moveu) return;
      if (foraDaArea(b)) enquadrar(b, desenharFios(b));
      b.enviar("mover", { id: parte.id, left: parte.left, top: parte.top, rotate: peca.rotacao });
    };
    caixa.addEventListener("pointermove", mover);
    caixa.addEventListener("pointerup", soltar, { once: true });
    caixa.addEventListener("pointercancel", soltar, { once: true });
  });
  caixa.addEventListener("dblclick", () => {
    if (!b.editavel) return;
    peca.rotacao = ((peca.rotacao || 0) + 90) % 360;
    caixa.style.transform = peca.rotacao ? "rotate(" + peca.rotacao + "deg)" : "";
    const pontos = desenharFios(b);
    if (foraDaArea(b)) enquadrar(b, pontos);
    b.enviar("mover", { id: parte.id, left: parte.left || 0, top: parte.top || 0, rotate: peca.rotacao });
  });
}

async function montar(b, dados) {
  const versao = ++b.versao;
  b.diagrama = JSON.parse(JSON.stringify(dados.diagrama || { parts: [], connections: [] }));
  b.telas = dados.telas || {};
  b.destaques = new Set(dados.destaques || []);
  // remove também as peças de um desenho interrompido, que não chegaram a b.pecas
  b.mesa.querySelectorAll(".peca, .rotulo").forEach((el) => el.remove());
  b.pecas = {};
  b.svg.replaceChildren();
  b.area.querySelector(".vazia")?.remove();
  if (!(b.diagrama.parts || []).length) {
    b.dica.textContent = "";
    b.area.insertAdjacentHTML("beforeend", '<div class="vazia"><b>Bancada vazia</b><span>Descreva no chat o circuito que você quer montar.<br>As peças e os fios aparecem aqui conforme o assistente monta.</span></div>');
    return;
  }
  try { await carregarBiblioteca(); } catch (e) { b.aviso.textContent = "Sem acesso às peças do Wokwi (CDN)."; return; }
  const pecas = {};
  for (const parte of b.diagrama.parts) {
    pecas[parte.id] = await montarPeca(b, parte);
    if (versao !== b.versao) return;  // outro desenho começou no meio deste
  }
  b.pecas = pecas;
  await new Promise((r) => setTimeout(r, 120));
  if (versao !== b.versao) return;
  const movidas = desembaracar(b);
  enquadrar(b, desenharFios(b));
  if (movidas.length && b.editavel) b.enviar("mover", { pecas: movidas });
  b.dica.textContent = b.editavel ? "Arraste para mover. Duplo clique gira." : "";
  atualizarAoVivo(b, b.ultimoDados);
}

function montarControles(b, controles) {
  b.controles.replaceChildren();
  if (!controles.length) {
    b.controles.innerHTML = '<div class="sem-controles">Este circuito não tem sensores nem botões para controlar.</div>';
    return;
  }
  for (const { parte, lista } of controles) {
    if (!lista.length) {
      const botao = document.createElement("button");
      botao.className = "botao"; botao.textContent = "Apertar " + parte;
      botao.addEventListener("pointerdown", () => b.enviar("botao", { parte, n: Date.now() }));
      b.controles.appendChild(botao);
      continue;
    }
    for (const c of lista) {
      const caixa = document.createElement("div");
      caixa.className = "controle";
      const passo = c.passo, casas = passo < 1 ? (passo < 0.1 ? 2 : 1) : 0;
      caixa.innerHTML = `<label><span>${parte}: ${c.rotulo}</span><b>${c.valor.toFixed(casas)}</b></label>` +
        `<input type="range" min="${c.minimo}" max="${c.maximo}" step="${passo}" value="${c.valor}">`;
      const entrada = caixa.querySelector("input"), valor = caixa.querySelector("b");
      entrada.addEventListener("input", () => { valor.textContent = Number(entrada.value).toFixed(casas); });
      entrada.addEventListener("change", () => b.enviar("controle", { parte, controle: c.controle, valor: Number(entrada.value) }));
      b.controles.appendChild(caixa);
    }
  }
}

function atualizarAoVivo(b, dados) {
  if (!dados) return;
  const v = dados.ao_vivo;
  b.aovivo.hidden = !v;
  for (const p of Object.values(b.pecas)) {
    if (p.parte.type === "wokwi-led" && p.elemento) p.elemento.value = !!(v && v.acesos && v.acesos[p.parte.id]);
  }
  if (!v) { b.controlesDe = null; return; }
  const chave = JSON.stringify(dados.controles || []);
  if (b.controlesDe !== chave) { b.controlesDe = chave; montarControles(b, dados.controles || []); }
  b.status.className = "status" + (v.iniciando ? " iniciando" : "");
  const m = Math.floor(v.restante / 60), s = String(v.restante % 60).padStart(2, "0");
  b.status.textContent = v.iniciando ? "Ligando a simulação no Wokwi..." : `Simulação ao vivo. Desliga sozinha em ${m}:${s}.`;
  const noFim = b.serial.scrollTop + b.serial.clientHeight >= b.serial.scrollHeight - 4;
  if (b.serial.textContent !== v.serial) {
    b.serial.textContent = v.serial || "(sem saída ainda)";
    if (noFim) b.serial.scrollTop = b.serial.scrollHeight;
  }
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  const raiz = parentElement.querySelector(".bancada");
  let b = raiz.__bancada;
  if (!b) b = raiz.__bancada = estrutura(raiz);
  b.enviar = setTriggerValue;
  b.editavel = data.editavel !== false;
  b.area.style.setProperty("--altura", (data.altura || 480) + "px");
  b.ultimoDados = data;
  // só redesenha quando peças, ligações, telas ou destaques mudam; posição mudada aqui já está na tela
  const telas = Object.entries(data.telas || {}).map(([k, t]) => k + t.length + t.slice(-24));
  const assinatura = JSON.stringify([(data.diagrama?.parts || []).map((p) => [p.id, p.type, p.attrs]),
                                     data.diagrama?.connections || [], telas, data.destaques || []]);
  if (assinatura !== b.assinatura) {
    b.assinatura = assinatura;
    montar(b, data);
  } else {
    atualizarAoVivo(b, data);
  }
}
""".replace("__VERSAO__", VERSAO_ELEMENTOS).replace("__COMMIT__", COMMIT_PLACAS)

_componente = st.components.v2.component("assistente_bancada_mesa", html=HTML, css=CSS, js=JS)


def mesa(chave, diagrama, telas=None, destaques=None, ao_vivo=None, controles=None, altura=480, editavel=True):
    """editavel=False durante a resposta: um evento reexecutaria o script e interromperia a resposta."""
    dados = {
        "diagrama": diagrama,
        "telas": telas or {},
        "destaques": sorted(destaques or []),
        "ao_vivo": ao_vivo,
        "controles": [
            {"parte": parte, "lista": [
                {"controle": c, "rotulo": r, "minimo": mi, "maximo": ma, "passo": pa, "valor": va}
                for c, r, mi, ma, pa, va in lista]}
            for parte, _tipo, lista in (controles or [])
        ],
        "altura": altura,
        "editavel": editavel,
    }
    return _componente(key=chave, data=dados, on_mover_change=lambda: None,
                       on_controle_change=lambda: None, on_botao_change=lambda: None)
