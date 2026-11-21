"""De onde vêm os memes: a meme-api.com (que lê o Reddit) e a pasta estoque/."""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import Config, Fonte

MEME_API = "https://meme-api.com/gimme/{subreddit}/{quantidade}"
QUANTIDADE_POR_BUSCA = 50  # máximo aceito pela meme-api
EXTENSOES_DE_IMAGEM = (".jpg", ".jpeg", ".png", ".gif", ".webp")
LIMITE_DE_UPLOAD = 10 * 1024 * 1024  # 10 MB: limite do Discord em servidor sem boost


class ErroDeFonte(Exception):
    pass


@dataclass
class Meme:
    fonte: str  # "reddit" ou "estoque"
    chave: str  # identifica o meme no histórico (link do post ou estoque/arquivo)
    titulo: str = ""
    imagem: str = ""  # URL da imagem (memes do Reddit)
    link: str = ""  # link do post original
    subreddit: str = ""
    votos_reddit: int = 0
    arquivo: Path | None = None  # memes do estoque


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).lower()
    return re.sub(r"[^a-z0-9]", "", texto)


def titulo_util(titulo: str, subreddit: str) -> str:
    """Devolve o título do post, ou "" se ele só repete o nome do subreddit (ex.: 'eu_nvr')."""
    if not titulo or _normalizar(titulo) in ("", _normalizar(subreddit)):
        return ""
    return titulo[:256]


def eh_imagem(url: str) -> bool:
    return url.lower().split("?")[0].endswith(EXTENSOES_DE_IMAGEM)


def buscar_memes(subreddit: str, sessao=None, quantidade: int = QUANTIDADE_POR_BUSCA) -> list[Meme]:
    """Memes recentes de um subreddit, já sem NSFW, spoilers e posts que não são imagem."""
    sessao = sessao or requests
    resposta = sessao.get(
        MEME_API.format(subreddit=subreddit, quantidade=quantidade),
        headers={"User-Agent": "memes-aleatorios (bot de Discord)"},
        timeout=30,
    )
    if resposta.status_code != 200:
        raise ErroDeFonte(f"a meme-api respondeu {resposta.status_code}")
    dados = resposta.json()
    if isinstance(dados, dict) and isinstance(dados.get("memes"), list):
        itens = dados["memes"]
    elif isinstance(dados, dict) and dados.get("url"):
        itens = [dados]
    else:
        detalhe = dados.get("message") if isinstance(dados, dict) else dados
        raise ErroDeFonte(f"a meme-api não trouxe memes ({detalhe})")

    memes = []
    for item in itens:
        url = str(item.get("url") or "")
        if item.get("nsfw") or item.get("spoiler") or not eh_imagem(url):
            continue
        link = str(item.get("postLink") or url)
        memes.append(
            Meme(
                fonte="reddit",
                chave=link,
                titulo=str(item.get("title") or ""),
                imagem=url,
                link=link,
                subreddit=str(item.get("subreddit") or subreddit),
                votos_reddit=int(item.get("ups") or 0),
            )
        )
    return memes


def ordem_das_fontes(fontes: tuple[Fonte, ...], rng: random.Random) -> list[Fonte]:
    """Sorteia a ordem das fontes respeitando o peso (peso maior costuma vir primeiro)."""
    return sorted(fontes, key=lambda fonte: rng.random() ** (1.0 / fonte.peso), reverse=True)


def escolher_do_reddit(config: Config, ja_postado: Callable[[Meme], bool], rng, sessao=None, log=print):
    for fonte in ordem_das_fontes(config.fontes, rng):
        try:
            memes = buscar_memes(fonte.subreddit, sessao)
        except (requests.RequestException, ErroDeFonte, ValueError) as erro:
            log(f"⚠️ Não consegui buscar memes de r/{fonte.subreddit}: {erro}")
            continue
        novos = [meme for meme in memes if not ja_postado(meme)]
        if novos:
            return max(novos, key=lambda meme: meme.votos_reddit)
        log(f"ℹ️ r/{fonte.subreddit}: nenhum meme novo agora (todos já saíram ou foram filtrados).")
    return None


def listar_estoque(pasta: Path) -> list[Path]:
    if not pasta.is_dir():
        return []
    return sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix.lower() in EXTENSOES_DE_IMAGEM)


def escolher_do_estoque(config: Config, ja_postado: Callable[[Meme], bool], rng, log=print):
    candidatos = []
    for arquivo in listar_estoque(config.estoque_pasta):
        meme = Meme(fonte="estoque", chave=f"estoque/{arquivo.name}", arquivo=arquivo)
        if ja_postado(meme):
            continue
        if arquivo.stat().st_size > LIMITE_DE_UPLOAD:
            log(f"⚠️ {arquivo.name} tem mais de 10 MB e o Discord não aceita. Pulei.")
            continue
        candidatos.append(meme)
    return rng.choice(candidatos) if candidatos else None


def escolher_meme(config: Config, ja_postado: Callable[[Meme], bool], rng=None, sessao=None, log=print):
    """Escolhe o próximo meme. Às vezes começa pelo estoque; se uma fonte falhar, tenta a outra."""
    rng = rng or random.Random()

    def do_reddit():
        return escolher_do_reddit(config, ja_postado, rng, sessao, log)

    def do_estoque():
        return escolher_do_estoque(config, ja_postado, rng, log)

    ordem = (do_estoque, do_reddit) if rng.random() < config.estoque_chance else (do_reddit, do_estoque)
    for escolher in ordem:
        meme = escolher()
        if meme is not None:
            return meme
    return None
