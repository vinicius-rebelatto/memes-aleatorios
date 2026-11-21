"""Peças falsas usadas nos testes: nada aqui acessa a internet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import carregar_config
from bot.discord_api import EPOCA_DISCORD_MS

CONFIG_DE_TESTE = """
fontes:
  - subreddit: eu_nvr
    peso: 3
  - subreddit: me_irl
    peso: 1
votacao:
  emoji_voto: "😂"
moderacao:
  emoji_remover: "🚫"
  votos_para_remover: 3
ranking:
  dias: 7
  quantidade: 3
  incluir_posts_da_galera: true
estoque:
  pasta: estoque
  chance: 0
"""


class RespostaFalsa:
    def __init__(self, status=200, corpo=None, headers=None):
        self.status_code = status
        self._corpo = corpo
        self.headers = headers or {}
        self.text = "" if corpo is None else json.dumps(corpo)
        self.content = self.text.encode()

    def json(self):
        if self._corpo is None:
            raise ValueError("sem corpo")
        return self._corpo


class SessaoFalsa:
    """Imita requests.Session: devolve as respostas na ordem e guarda cada chamada."""

    def __init__(self, respostas=None):
        self.respostas = list(respostas or [])
        self.chamadas = []

    def request(self, metodo, url, **opcoes):
        self.chamadas.append((metodo, url, opcoes))
        if not self.respostas:
            raise AssertionError(f"chamada inesperada: {metodo} {url}")
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def get(self, url, **opcoes):
        return self.request("GET", url, **opcoes)


class SessaoPorSubreddit:
    """Imita a meme-api: responde conforme o subreddit pedido na URL."""

    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.pedidos = []

    def get(self, url, **opcoes):
        for subreddit, resposta in self.respostas.items():
            if f"/gimme/{subreddit}/" in url:
                self.pedidos.append(subreddit)
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        raise AssertionError(f"URL inesperada: {url}")


class RngFixo:
    """Sorteio previsível: random() sempre igual e choice() pega o primeiro."""

    def __init__(self, valor=0.5):
        self.valor = valor

    def random(self):
        return self.valor

    def choice(self, itens):
        return itens[0]


class DiscordFalso:
    def __init__(self, mensagens=None, bot_id="999", servidor_id="111"):
        self.mensagens_do_canal = list(mensagens or [])
        self.bot_id = bot_id
        self.servidor_id = servidor_id
        self.enviadas = []
        self.reacoes = []
        self.apagadas = []
        self.dormidas = []
        self.proximo_id = 5000

    def canal(self, canal_id):
        return {"id": canal_id, "guild_id": self.servidor_id}

    def eu(self):
        return {"id": self.bot_id}

    def enviar(self, canal_id, corpo, anexo=None):
        self.proximo_id += 1
        self.enviadas.append({"canal": canal_id, "corpo": corpo, "anexo": anexo})
        return {"id": str(self.proximo_id)}

    def reagir(self, canal_id, mensagem_id, emoji):
        self.reacoes.append((mensagem_id, emoji))

    def apagar(self, canal_id, mensagem_id):
        self.apagadas.append(mensagem_id)

    def mensagens(self, canal_id, limite=100, antes=None):
        return self.mensagens_do_canal[:limite]

    def mensagens_desde(self, canal_id, desde_ms):
        return list(self.mensagens_do_canal)

    def dormir(self, segundos):
        self.dormidas.append(segundos)


def item_da_api(numero, ups=10, subreddit="eu_nvr", titulo=None, nsfw=False, spoiler=False, url=None):
    """Um meme no formato que a meme-api devolve."""
    return {
        "postLink": f"https://redd.it/post{numero}",
        "subreddit": subreddit,
        "title": titulo if titulo is not None else subreddit,
        "url": url or f"https://i.redd.it/imagem{numero}.png",
        "nsfw": nsfw,
        "spoiler": spoiler,
        "author": "alguem",
        "ups": ups,
        "preview": [],
    }


def resposta_da_api(*itens):
    return RespostaFalsa(200, {"count": len(itens), "memes": list(itens)})


def snowflake(ms: int) -> str:
    """ID de mensagem do Discord criada no instante `ms` (milissegundos)."""
    return str((ms - EPOCA_DISCORD_MS) << 22)


def reacao(emoji, quantidade, do_bot=False):
    return {"emoji": {"id": None, "name": emoji}, "count": quantidade, "me": do_bot}


@pytest.fixture
def config(tmp_path):
    (tmp_path / "estoque").mkdir()
    caminho = tmp_path / "config.yml"
    caminho.write_text(CONFIG_DE_TESTE, encoding="utf-8")
    return carregar_config(caminho)
