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
from .termometro import Termometro, proximidade

MEME_API = "https://meme-api.com/gimme/{subreddit}/{quantidade}"
QUANTIDADE_POR_BUSCA = 50  # máximo aceito pela meme-api
EXTENSOES_DE_IMAGEM = (".jpg", ".jpeg", ".png", ".gif", ".webp")
LIMITE_DE_UPLOAD = 10 * 1024 * 1024  # 10 MB: limite do Discord em servidor sem boost

# Os IDs de post do Reddit são sequenciais, então dá para estimar a idade de um post
# comparando o ID dele com o do post mais novo da mesma busca.
IDS_POR_DIA = 1_450_000  # quantos posts o Reddit inteiro recebe por dia (aproximado)
MEIA_VIDA_DIAS = 3  # a cada 3 dias de idade, o meme passa a valer metade
IDADE_MAXIMA_DIAS = 60  # mais velho que isso não entra (os subs brasileiros são mais lentos)


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
    nsfw: bool = False
    nivel: float | None = None  # nível de peso usado na régua (fonte + 1 se for NSFW)
    id_reddit: int | None = None
    categoria: str = ""


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


def id_do_post(link: str) -> int | None:
    """Número do post no Reddit, tirado do link (redd.it/abc123 ou .../comments/abc123/...)."""
    achado = re.search(r"(?://redd\.it/|/comments/)([0-9a-z]+)", link or "", re.IGNORECASE)
    if not achado:
        return None
    try:
        return int(achado.group(1).lower(), 36)
    except ValueError:
        return None


def buscar_memes(subreddit: str, sessao=None, quantidade: int = QUANTIDADE_POR_BUSCA) -> list[Meme]:
    """Memes recentes de um subreddit, sem spoilers e sem posts que não são imagem."""
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
        if item.get("spoiler") or not eh_imagem(url):
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
                nsfw=bool(item.get("nsfw")),
                id_reddit=id_do_post(link),
            )
        )
    return memes


def enviados_pelo_comando(endereco: str | None, sessao=None) -> set[str]:
    """Links que o /meme já mandou (o Worker guarda). Se o Worker não responder, segue sem eles."""
    if not endereco:
        return set()
    try:
        resposta = (sessao or requests).get(f"{endereco}/enviados", timeout=10)
        if resposta.status_code != 200:
            return set()
        return {str(link) for link in resposta.json().get("links", []) if link}
    except (requests.RequestException, ValueError, AttributeError):
        return set()


def baixar_imagem(url: str, sessao=None, limite: int = LIMITE_DE_UPLOAD) -> bytes | None:
    """Baixa a imagem do meme para postar como arquivo. None se falhar ou passar do limite do Discord."""
    sessao = sessao or requests
    try:
        resposta = sessao.get(url, headers={"User-Agent": "memes-aleatorios (bot de Discord)"}, timeout=30)
    except requests.RequestException:
        return None
    tipo = str(resposta.headers.get("Content-Type", "")).lower()
    conteudo = resposta.content or b""
    if resposta.status_code != 200 or not tipo.startswith("image/") or not 0 < len(conteudo) <= limite:
        return None
    return conteudo


def idade_em_dias(meme: Meme, id_mais_novo: int | None) -> float | None:
    if meme.id_reddit is None or id_mais_novo is None:
        return None
    return max(0, id_mais_novo - meme.id_reddit) / IDS_POR_DIA


def pontuar(meme: Meme, id_mais_novo: int | None, regua: float | None = None) -> float:
    """Nota do meme dentro da fonte: votos no Reddit, descontando a idade e a distância da régua."""
    pontos = meme.votos_reddit + 1.0
    idade = idade_em_dias(meme, id_mais_novo)
    if idade is not None:
        pontos *= 0.5 ** (idade / MEIA_VIDA_DIAS)
    if regua is not None and meme.nivel is not None:
        pontos *= proximidade(meme.nivel, regua)
    return pontos


def candidatos_da_fonte(
    fonte: Fonte,
    memes: list[Meme],
    ja_postado: Callable[[Meme], bool],
    permitir_nsfw: bool,
    votos_minimos: int = 0,
    bloquear: tuple[str, ...] = (),
) -> tuple[list[Meme], int | None]:
    """Os memes que podem sair: inéditos, recentes, com votos suficientes no Reddit, sem palavra
    bloqueada no título e (se o canal não for +18) sem NSFW.

    Devolve (candidatos, id do post mais novo da busca), que serve para calcular a idade.
    """
    ids = [meme.id_reddit for meme in memes if meme.id_reddit is not None]
    id_mais_novo = max(ids) if ids else None
    candidatos = []
    for meme in memes:
        idade = idade_em_dias(meme, id_mais_novo)
        if ja_postado(meme) or (meme.nsfw and not permitir_nsfw):
            continue
        if idade is not None and idade > IDADE_MAXIMA_DIAS:
            continue
        if meme.votos_reddit < votos_minimos:
            continue
        titulo = meme.titulo.lower()
        if any(palavra in titulo for palavra in bloquear):
            continue
        meme.categoria = fonte.categoria
        if fonte.segue_a_regua:
            meme.nivel = min(5.0, fonte.nivel + (1 if meme.nsfw else 0))
        candidatos.append(meme)
    return candidatos, id_mais_novo


def ordem_das_fontes(fontes: tuple[Fonte, ...], pesos: dict[str, float], rng) -> list[Fonte]:
    """Sorteia a ordem das fontes: quanto maior o peso, maior a chance de vir primeiro."""

    def chave(fonte: Fonte) -> float:
        peso = pesos.get(fonte.subreddit, 0.0)
        return rng.random() ** (1.0 / peso) if peso > 0 else -1.0

    return sorted(fontes, key=chave, reverse=True)


def escolher_do_reddit(
    config: Config,
    ja_postado: Callable[[Meme], bool],
    rng,
    sessao=None,
    log=print,
    termometro: Termometro | None = None,
    permitir_nsfw: bool = False,
):
    surpresa = termometro is None or rng.random() < config.surpresa
    if termometro is None:
        pesos = {fonte.subreddit: fonte.peso for fonte in config.fontes}
    else:
        if surpresa:
            log("🎲 Post surpresa: sorteando a categoria sem olhar a régua.")
        pesos = termometro.pesos(config.fontes, surpresa=surpresa)
    regua = None if surpresa else termometro.regua

    for fonte in ordem_das_fontes(config.fontes, pesos, rng):
        try:
            memes = buscar_memes(fonte.subreddit, sessao)
        except (requests.RequestException, ErroDeFonte, ValueError) as erro:
            log(f"⚠️ Não consegui buscar memes de r/{fonte.subreddit}: {erro}")
            continue
        candidatos, id_mais_novo = candidatos_da_fonte(
            fonte, memes, ja_postado, permitir_nsfw, config.votos_minimos, config.bloquear
        )
        if candidatos:
            return max(candidatos, key=lambda meme: pontuar(meme, id_mais_novo, regua))
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


def escolher_meme(
    config: Config,
    ja_postado: Callable[[Meme], bool],
    rng=None,
    sessao=None,
    log=print,
    termometro: Termometro | None = None,
    permitir_nsfw: bool = False,
):
    """Escolhe o próximo meme. Às vezes começa pelo estoque; se uma fonte falhar, tenta a outra."""
    rng = rng or random.Random()

    def do_reddit():
        return escolher_do_reddit(config, ja_postado, rng, sessao, log, termometro, permitir_nsfw)

    def do_estoque():
        return escolher_do_estoque(config, ja_postado, rng, log)

    ordem = (do_estoque, do_reddit) if rng.random() < config.estoque_chance else (do_reddit, do_estoque)
    for escolher in ordem:
        meme = escolher()
        if meme is not None:
            return meme
    return None
