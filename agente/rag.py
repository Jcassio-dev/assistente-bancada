"""RAG: embeddings, acesso ao índice Chroma e ferramenta buscar_documentos.

O modelo multilingual-e5-small exige prefixos: "passage: " nos trechos
indexados e "query: " nas consultas. Os dois lados passam por este módulo
(embutir_trechos e embutir_consulta), então o prefixo nunca fica de fora.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path

import chromadb
from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from langchain_core.tools import tool

RAIZ = Path(__file__).resolve().parent.parent
PASTA_INDICE = RAIZ / "dados" / "indice"
PASTA_MODELOS = RAIZ / "dados" / "modelos"
COLECAO = "documentos"
MODELO = "intfloat/multilingual-e5-small"


@lru_cache(maxsize=1)
def modelo_embeddings():
    # O e5-small não está na lista padrão do fastembed: registramos o ONNX oficial do repositório.
    if MODELO not in {m["model"] for m in TextEmbedding.list_supported_models()}:
        TextEmbedding.add_custom_model(
            model=MODELO,
            pooling=PoolingType.MEAN,
            normalization=True,
            sources=ModelSource(hf=MODELO),
            dim=384,
            model_file="onnx/model.onnx",
        )
    # Na primeira execução baixa o modelo (~470 MB) para dados/modelos/.
    return TextEmbedding(MODELO, cache_dir=str(PASTA_MODELOS))


def embutir_trechos(textos):
    return [v.tolist() for v in modelo_embeddings().embed([f"passage: {t}" for t in textos], batch_size=32)]


def embutir_consulta(consulta):
    return next(iter(modelo_embeddings().embed([f"query: {consulta}"]))).tolist()


@lru_cache(maxsize=1)
def colecao():
    cliente = chromadb.PersistentClient(path=str(PASTA_INDICE))
    return cliente.get_collection(COLECAO)


# ---------- BM25 (busca por palavra-chave, para termos exatos como GPIO34, ADC2) ----------

def tokenizar(texto):
    return re.findall(r"[a-z0-9_]+", texto.lower())


@lru_cache(maxsize=1)
def indice_bm25():
    dados = colecao().get(include=["documents", "metadatas"])
    tokens = [tokenizar(t) for t in dados["documents"]]
    df = Counter(tok for doc in tokens for tok in set(doc))
    return {
        "ids": dados["ids"],
        "metadatas": dados["metadatas"],
        "documents": dados["documents"],
        "frequencias": [Counter(doc) for doc in tokens],
        "tamanhos": [len(doc) for doc in tokens],
        "media": sum(len(doc) for doc in tokens) / max(len(tokens), 1),
        "idf": {tok: math.log(1 + (len(tokens) - n + 0.5) / (n + 0.5)) for tok, n in df.items()},
    }


def buscar_bm25(consulta, documento=None, k=20, k1=1.5, b=0.75):
    ind = indice_bm25()
    termos = tokenizar(consulta)
    pontos = []
    for i, freq in enumerate(ind["frequencias"]):
        if documento and ind["metadatas"][i]["documento"] != documento:
            continue
        s = 0.0
        for t in termos:
            if t in freq:
                f = freq[t]
                s += ind["idf"][t] * f * (k1 + 1) / (f + k1 * (1 - b + b * ind["tamanhos"][i] / ind["media"]))
        if s > 0:
            pontos.append((s, i))
    pontos.sort(reverse=True)
    return [ind["ids"][i] for _, i in pontos[:k]]


# ---------- busca ----------

def buscar(consulta, documento=None, k=5, modo="hibrido"):
    """Devolve até k trechos [{id, texto, documento, titulo, pagina, secao, url, pontuacao}].

    modo="denso": só embeddings; pontuação = similaridade de cosseno (0 a 1).
    modo="hibrido": intercala os resultados dos embeddings e do BM25 (denso 1,
    BM25 1, denso 2, ...). Testamos Reciprocal Rank Fusion antes, mas ele
    perdia o 1º lugar do BM25 em perguntas de termo exato (GPIO12/MTDI).
    A pontuação continua sendo a similaridade de cosseno do trecho.
    """
    filtro = {"documento": documento} if documento else None
    candidatos = k if modo == "denso" else 2 * k
    r = colecao().query(
        query_embeddings=[embutir_consulta(consulta)],
        n_results=candidatos,
        where=filtro,
        include=["documents", "metadatas", "distances"],
    )
    trechos = {
        id_: {"id": id_, "texto": doc, **meta, "pontuacao": round(1 - dist, 3)}
        for id_, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])
    }
    if modo == "denso":
        return list(trechos.values())

    melhores = []
    for par in zip_longest(r["ids"][0], buscar_bm25(consulta, documento, k=candidatos)):
        for id_ in par:
            if id_ and id_ not in melhores:
                melhores.append(id_)
    melhores = melhores[:k]

    faltando = [i for i in melhores if i not in trechos]
    if faltando:
        extra = colecao().get(ids=faltando, include=["documents", "metadatas", "embeddings"])
        q = embutir_consulta(consulta)
        for id_, doc, meta, emb in zip(extra["ids"], extra["documents"], extra["metadatas"], extra["embeddings"]):
            cos = sum(a * b for a, b in zip(q, emb))  # vetores já normalizados
            trechos[id_] = {"id": id_, "texto": doc, **meta, "pontuacao": round(cos, 3)}
    return [trechos[i] for i in melhores]


def formatar_trechos(trechos):
    blocos = []
    for i, t in enumerate(trechos, 1):
        pagina = f"p. {t['pagina']}" if t["pagina"] else "página web"
        cabecalho = f"[{i}] {t['titulo']} ({t['documento']}), {pagina}"
        if t["secao"]:
            cabecalho += f", seção \"{t['secao']}\""
        blocos.append(f"{cabecalho}, pontuação {t['pontuacao']}\nFonte: {t['url']}\n{t['texto']}")
    return "\n\n".join(blocos)


@lru_cache(maxsize=1)
def documentos_indexados():
    return sorted({m["documento"] for m in indice_bm25()["metadatas"]})


@tool(response_format="content_and_artifact")
def buscar_documentos(consulta: str, documento: str | None = None) -> tuple[str, list[dict]]:
    """Busca trechos nos datasheets e manuais indexados (ESP32, sensores, Wokwi, JLCPCB).

    Escreva a consulta em inglês, com os termos técnicos do datasheet
    (ex.: "GPIO maximum source current", "ADC2 Wi-Fi restriction").
    documento (opcional) restringe a busca a um documento pelo id, ex.:
    esp32-datasheet, esp32-trm, esp32-hardware-design, dht22, ssd1306, jlcpcb.
    Se os trechos não responderem, reformule a consulta e busque de novo.
    """
    if documento and documento not in documentos_indexados():
        return f"Documento '{documento}' não existe. Use um destes: {', '.join(documentos_indexados())}.", []
    trechos = buscar(consulta, documento)
    if not trechos:
        return "Nenhum trecho encontrado. Reformule a consulta.", []
    return formatar_trechos(trechos), trechos
