"""Conversas da interface: cada conversa é uma bancada, com seu projeto e seu histórico.

A memória do agente (mensagens, ferramentas) fica no checkpointer SQLite, com o id
da conversa como thread_id. Aqui fica só o que a tela precisa: título, projeto,
etapas do protótipo e o histórico já formatado com os bastidores de cada resposta.
Tudo em dados/conversas/ (fora do git).
"""

import json
import re
import time
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dados" / "conversas"
MEMORIA = PASTA / "memoria.sqlite"
REGEX_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def nova(projeto=None):
    agora = time.time()
    return {
        "id": str(uuid.uuid4()),
        "titulo": projeto or "Nova bancada",
        "projeto": projeto,
        "criada": agora,
        "atualizada": agora,
        "historico": [],  # [{papel, texto, bastidores}]
        "etapas": {},  # validado, compilado, memoria, simulado, serial_ok
        "diagrama": None,  # última versão exibida (base para destacar o que mudou)
        "destaques": [],
        "serial": "",
    }


def caminho(id_):
    if not REGEX_ID.match(id_ or ""):
        raise ValueError("id de conversa inválido")
    return PASTA / f"{id_}.json"


def salvar(conversa):
    PASTA.mkdir(parents=True, exist_ok=True)
    conversa["atualizada"] = time.time()
    caminho(conversa["id"]).write_text(json.dumps(conversa, ensure_ascii=False), encoding="utf-8")


def carregar(id_):
    """A conversa salva, ou None se não existir (ou o id for inválido)."""
    try:
        arquivo = caminho(id_)
    except ValueError:
        return None
    return json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else None


def listar():
    """Conversas salvas, da mais recente para a mais antiga (só os campos da barra lateral)."""
    itens = []
    for arquivo in PASTA.glob("*.json"):
        try:
            c = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        itens.append({k: c.get(k) for k in ("id", "titulo", "projeto", "atualizada")})
    return sorted(itens, key=lambda c: c["atualizada"] or 0, reverse=True)


def quando(instante, agora=None):
    """'agora', 'há 5 min', 'há 3 h', 'ontem' ou 'há 4 dias'."""
    segundos = max(0, (agora or time.time()) - (instante or 0))
    if segundos < 60:
        return "agora"
    if segundos < 3600:
        return f"há {int(segundos // 60)} min"
    if segundos < 86400:
        return f"há {int(segundos // 3600)} h"
    dias = int(segundos // 86400)
    return "ontem" if dias == 1 else f"há {dias} dias"


def apagar(id_):
    try:
        caminho(id_).unlink(missing_ok=True)
    except ValueError:
        pass


def titulo_do_pedido(texto, limite=42):
    """Título curto a partir do primeiro pedido, enquanto a conversa não tem projeto."""
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 3].rstrip() + "..."
