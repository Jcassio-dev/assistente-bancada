"""Uso: python scripts/indexar.py"""

import re
import sys
import unicodedata
from pathlib import Path

import chromadb
import pymupdf
from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from agente.rag import COLECAO, PASTA_INDICE, embutir_trechos  # noqa: E402
from scripts.baixar_documentos import caminho_local, carregar_fontes  # noqa: E402

TAMANHO_TRECHO = 1200  # caracteres (~300 tokens; o e5 aceita até 512)
SOBREPOSICAO = 200
MARGEM = 0.06  # cabeçalho e rodapé da página (fração da altura) são descartados


def normalizar(texto):
    texto = unicodedata.normalize("NFKC", texto)
    # remove caracteres de uso privado e de largura zero (ícones de link nos títulos)
    texto = "".join(c for c in texto if unicodedata.category(c) not in ("Co", "Cf"))
    return re.sub(r"\s+", " ", texto).strip()


def sem_repeticoes(texto):
    """O PDF do DHT22 desenha cada palavra 4 vezes para simular negrito."""
    texto = re.sub(r"(?<!\S)(\S+)(?:\s+\1){2,}(?!\S)", r"\1", texto)
    return re.sub(r"(?<!\S)(\S{1,3}?)\1{2,}(?!\S)", r"\1", texto)


def sem_numeracao(titulo):
    return re.sub(r"^(\d+(\.\d+)*|[IVX]+)\s+", "", titulo).strip()


def paginas_dos_capitulos(doc, capitulos):
    toc = doc.get_toc()
    paginas, faltando = set(), []
    for nome in capitulos:
        achou = False
        for i, (nivel, titulo, pagina) in enumerate(toc):
            if not sem_numeracao(titulo).lower().startswith(nome.lower()):
                continue
            fim = doc.page_count
            for nivel2, _, pagina2 in toc[i + 1:]:
                if nivel2 <= nivel:
                    fim = pagina2
                    break
            paginas.update(range(pagina - 1, fim))
            achou = True
            break
        if not achou:
            faltando.append(nome)
    if faltando:
        titulos = "\n  ".join(f"{'  ' * (n - 1)}{t}" for n, t, _ in toc if n <= 3)
        sys.exit(f"Capítulos não encontrados: {faltando}\nMarcadores disponíveis:\n  {titulos}")
    return sorted(paginas)


def celulas(pagina, tabela):
    """O extract() do pymupdf embaralha números ('–0.3' vira '03 – .'): lê cada célula recortada."""
    return [
        [sem_repeticoes(normalizar(pagina.get_text("text", clip=pymupdf.Rect(c)))) if c else "" for c in linha.cells]
        for linha in tabela.rows
    ]


def tabela_para_linhas(linhas):
    if not linhas:
        return []
    cabecalho = linhas[0]
    for j in range(1, len(cabecalho)):  # célula mesclada no cabeçalho: herda da esquerda
        if not cabecalho[j]:
            cabecalho[j] = cabecalho[j - 1]
    if len(linhas) == 1:
        return [" | ".join(c for c in cabecalho if c)]
    saida = []
    anterior = [""] * len(cabecalho)
    for linha in linhas[1:]:
        # célula mesclada na vertical (ex.: nome do pino ocupando várias linhas): herda de cima
        linha = [c or (anterior[j] if j == 0 else "") for j, c in enumerate(linha)]
        anterior = linha
        partes = [f"{cabecalho[j]}: {c}" if cabecalho[j] else c for j, c in enumerate(linha) if c]
        if partes:
            saida.append(" | ".join(partes))
    return saida


def extrair_pdf(caminho, capitulos):
    doc = pymupdf.open(caminho)
    paginas = paginas_dos_capitulos(doc, capitulos) if capitulos else range(doc.page_count)
    marcadores = {}
    for _, titulo, pagina in doc.get_toc():
        marcadores.setdefault(pagina - 1, []).append(titulo)

    secao = ""
    for p in range(min(paginas, default=0)):  # seção vigente no início da primeira página
        if p in marcadores:
            secao = marcadores[p][-1]
    itens = []
    for p in paginas:
        pagina = doc[p]
        altura = pagina.rect.height
        topo, base = altura * MARGEM, altura * (1 - MARGEM)

        tabelas = list(pagina.find_tables())
        caixas = [pymupdf.Rect(t.bbox) for t in tabelas]
        elementos = []
        for t, caixa in zip(tabelas, caixas):
            linhas = tabela_para_linhas(celulas(pagina, t))
            if linhas:
                elementos.append((caixa.y0, "\n".join(linhas)))
        for x0, y0, x1, y1, texto, *_ in pagina.get_text("blocks"):
            bloco = pymupdf.Rect(x0, y0, x1, y1)
            if y1 < topo or y0 > base or any(bloco.intersects(c) for c in caixas):
                continue
            texto = sem_repeticoes(normalizar(texto))
            if texto:
                elementos.append((y0, texto))
        elementos.sort(key=lambda e: e[0])

        # Troca de seção quando um bloco desta página começa com o título de um marcador
        # (só "contém" não basta: o texto cita outras seções, ex. "see Section 5.2 ...").
        titulos = list(marcadores.get(p, []))
        for _, texto in elementos:
            while titulos and texto.lower().startswith(normalizar(titulos[0]).lower()):
                secao = titulos.pop(0)
            itens.append((p + 1, secao, texto))
        if titulos:  # títulos não achados no texto: valem a partir da próxima página
            secao = titulos[-1]
    return itens


def extrair_html(caminho):
    sopa = BeautifulSoup(caminho.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for lixo in sopa(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg"]):
        lixo.decompose()
    principal = sopa.find("article") or sopa.find(attrs={"role": "main"}) or sopa.find("main") or sopa.body

    secao, itens, ultimo_cabecalho = "", [], None
    for el in principal.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "table", "dt", "dd"]):
        if el.name != "table" and el.find_parent("table"):
            continue
        if el.name == "p" and el.find_parent("li"):
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            secao = normalizar(el.get_text(" ")).strip(" #")
            itens.append((0, secao, secao))
            continue
        if el.name == "table":
            linhas = [[normalizar(c.get_text(" ")) for c in tr.find_all(["th", "td"])] for tr in el.find_all("tr")]
            if el.find("th"):
                ultimo_cabecalho = linhas[0]
                if len(linhas) == 1:  # tabela só de cabeçalho (JLCPCB): vale para a próxima
                    continue
            elif ultimo_cabecalho:
                linhas = [ultimo_cabecalho] + linhas
            texto = "\n".join(_linhas_tabela_html(linhas))
        elif el.name == "li":
            # só o texto do próprio item, sem as sublistas (que aparecem como itens próprios)
            partes = [c.get_text(" ") if hasattr(c, "get_text") else str(c)
                      for c in el.contents if getattr(c, "name", None) not in ("ul", "ol")]
            texto = "- " + normalizar(" ".join(partes))
        else:
            texto = normalizar(el.get_text(" "))
        if texto.strip("- "):
            itens.append((0, secao, texto))
    return itens


def _linhas_tabela_html(linhas):
    if not linhas:
        return []
    cabecalho, saida = linhas[0], []
    for linha in linhas[1:]:
        partes = [f"{cabecalho[j]}: {c}" if j < len(cabecalho) and cabecalho[j] else c
                  for j, c in enumerate(linha) if c]
        if partes:
            saida.append(" | ".join(partes))
    return saida or [" | ".join(cabecalho)]


def dividir(itens):
    minimo = 200  # trecho menor que isso (ex.: só o título) é juntado ao seguinte
    unidades = []
    for pagina, secao, texto in itens:
        for linha in texto.split("\n") if len(texto) > TAMANHO_TRECHO else [texto]:
            unidades.append((pagina, secao, linha[: TAMANHO_TRECHO * 2]))

    trechos, atual = [], []
    def fechar():
        if atual:
            # a seção do trecho é a que ocupa mais texto nele (não a de um título que veio junto)
            peso = {}
            for u in atual:
                peso[u[1]] = peso.get(u[1], 0) + len(u[2])
            secao = max(peso, key=peso.get)
            trechos.append({"pagina": atual[0][0], "secao": secao, "texto": "\n".join(u[2] for u in atual)})

    for unidade in unidades:
        tamanho = sum(len(u[2]) + 1 for u in atual)
        mudou_secao = unidade[1] != atual[-1][1] if atual else False
        if atual and ((mudou_secao and tamanho >= minimo) or tamanho + len(unidade[2]) > TAMANHO_TRECHO):
            fechar()
            # sobreposição: repete o fim do trecho anterior se for da mesma seção
            mesmo = [u for u in atual if u[1] == unidade[1]]
            atual, acumulado = [], 0
            for u in reversed(mesmo):
                if acumulado + len(u[2]) > SOBREPOSICAO:
                    break
                atual.insert(0, u)
                acumulado += len(u[2])
        atual.append(unidade)
    fechar()
    return trechos


def main():
    cliente = chromadb.PersistentClient(path=str(PASTA_INDICE))
    if COLECAO in [c.name for c in cliente.list_collections()]:
        cliente.delete_collection(COLECAO)
    colecao = cliente.create_collection(COLECAO, metadata={"hnsw:space": "cosine"})

    total = 0
    for doc in carregar_fontes():
        caminho = caminho_local(doc)
        if not caminho.exists():
            sys.exit(f"{caminho} não existe. Rode antes: python scripts/baixar_documentos.py")
        itens = extrair_pdf(caminho, doc.get("capitulos")) if doc["tipo"] == "pdf" else extrair_html(caminho)
        trechos = dividir(itens)
        # O texto embutido leva título e seção na frente: ajuda a recuperar trechos curtos de tabela.
        textos_embutidos = [f"{doc['titulo']} - {t['secao']}\n{t['texto']}" for t in trechos]
        colecao.add(
            ids=[f"{doc['id']}-{i:04d}" for i in range(len(trechos))],
            documents=[t["texto"] for t in trechos],
            embeddings=embutir_trechos(textos_embutidos),
            metadatas=[
                {
                    "documento": doc["id"],
                    "titulo": doc["titulo"],
                    "pagina": t["pagina"],  # página do PDF (0 = página web)
                    "secao": t["secao"],
                    "url": doc["url"],
                    "origem": doc["origem"],
                }
                for t in trechos
            ],
        )
        paginas = len({t["pagina"] for t in trechos})
        print(f"{doc['id']:24} {len(trechos):5} trechos  {paginas:4} páginas")
        total += len(trechos)
    print(f"Total: {total} trechos em {PASTA_INDICE}")


if __name__ == "__main__":
    main()
