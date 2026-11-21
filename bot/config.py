"""Lê o config.yml e os segredos (DISCORD_TOKEN e DISCORD_CHANNEL_ID)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PADRAO = RAIZ / "config.yml"


class ErroDeConfiguracao(Exception):
    """Problema de configuração, com uma mensagem pensada para quem lê o log."""


class SegredosAusentes(ErroDeConfiguracao):
    """Nenhum segredo configurado ainda: o bot ainda não foi instalado."""


@dataclass(frozen=True)
class Fonte:
    subreddit: str
    peso: float = 1.0


@dataclass(frozen=True)
class Config:
    fontes: tuple[Fonte, ...]
    emoji_voto: str = "😂"
    emoji_remover: str = "🚫"
    votos_para_remover: int = 3
    ranking_dias: int = 7
    ranking_quantidade: int = 3
    ranking_incluir_galera: bool = True
    estoque_pasta: Path = RAIZ / "estoque"
    estoque_chance: float = 0.2
    historico: Path = RAIZ / "dados" / "historico.json"


def _secao(dados: dict, nome: str) -> dict:
    valor = dados.get(nome) or {}
    if not isinstance(valor, dict):
        raise ErroDeConfiguracao(f"No config.yml, '{nome}' deveria ser uma seção com itens 'chave: valor'.")
    return valor


def _numero(valor, nome: str, tipo=float):
    try:
        return tipo(valor)
    except (TypeError, ValueError):
        raise ErroDeConfiguracao(f"No config.yml, '{nome}' precisa ser um número (veio '{valor}').") from None


def carregar_config(caminho: Path | str = CONFIG_PADRAO) -> Config:
    caminho = Path(caminho)
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise ErroDeConfiguracao(f"Não achei o arquivo {caminho.name}.") from None
    except yaml.YAMLError as erro:
        raise ErroDeConfiguracao(f"O {caminho.name} tem um erro de formatação: {erro}") from None
    if not isinstance(dados, dict):
        raise ErroDeConfiguracao(f"O {caminho.name} não está no formato esperado.")

    fontes = []
    for item in dados.get("fontes") or []:
        if isinstance(item, str):
            item = {"subreddit": item}
        if not isinstance(item, dict) or not item.get("subreddit"):
            raise ErroDeConfiguracao("Cada item de 'fontes' no config.yml precisa ter 'subreddit'.")
        nome = str(item["subreddit"]).strip().strip("/").removeprefix("r/")
        peso = _numero(item.get("peso", 1), f"peso de r/{nome}")
        if peso <= 0:
            raise ErroDeConfiguracao(f"O peso de r/{nome} precisa ser maior que zero.")
        fontes.append(Fonte(nome, peso))
    if not fontes:
        raise ErroDeConfiguracao("O config.yml precisa ter pelo menos uma fonte em 'fontes'.")

    votacao = _secao(dados, "votacao")
    moderacao = _secao(dados, "moderacao")
    ranking = _secao(dados, "ranking")
    estoque = _secao(dados, "estoque")

    votos_para_remover = _numero(moderacao.get("votos_para_remover", 3), "moderacao.votos_para_remover", int)
    if votos_para_remover < 1:
        raise ErroDeConfiguracao("moderacao.votos_para_remover precisa ser pelo menos 1.")
    dias = _numero(ranking.get("dias", 7), "ranking.dias", int)
    quantidade = _numero(ranking.get("quantidade", 3), "ranking.quantidade", int)
    if dias < 1 or quantidade < 1:
        raise ErroDeConfiguracao("ranking.dias e ranking.quantidade precisam ser pelo menos 1.")
    chance = _numero(estoque.get("chance", 0.2), "estoque.chance")
    if not 0 <= chance <= 1:
        raise ErroDeConfiguracao("estoque.chance precisa estar entre 0 e 1 (ex.: 0.2 = 20%).")

    pasta = Path(str(estoque.get("pasta", "estoque")))
    if not pasta.is_absolute():
        pasta = caminho.parent / pasta

    return Config(
        fontes=tuple(fontes),
        emoji_voto=str(votacao.get("emoji_voto", "😂")).strip(),
        emoji_remover=str(moderacao.get("emoji_remover", "🚫")).strip(),
        votos_para_remover=votos_para_remover,
        ranking_dias=dias,
        ranking_quantidade=quantidade,
        ranking_incluir_galera=bool(ranking.get("incluir_posts_da_galera", True)),
        estoque_pasta=pasta,
        estoque_chance=chance,
        historico=caminho.parent / "dados" / "historico.json",
    )


def _limpar(valor: str | None) -> str:
    return (valor or "").strip().strip('"').strip("'").strip()


def ler_segredos(ambiente: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Lê o token do bot e o ID do canal das variáveis de ambiente (secrets do GitHub)."""
    ambiente = os.environ if ambiente is None else ambiente
    token = _limpar(ambiente.get("DISCORD_TOKEN"))
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    canal = _limpar(ambiente.get("DISCORD_CHANNEL_ID"))

    if not token and not canal:
        raise SegredosAusentes(
            "Os secrets DISCORD_TOKEN e DISCORD_CHANNEL_ID ainda não foram configurados no GitHub "
            "(passo 3 do README). Nada foi feito."
        )
    faltando = [nome for nome, valor in (("DISCORD_TOKEN", token), ("DISCORD_CHANNEL_ID", canal)) if not valor]
    if faltando:
        raise ErroDeConfiguracao(f"Falta configurar o secret {' e '.join(faltando)} no GitHub (passo 3 do README).")
    if not canal.isdigit():
        raise ErroDeConfiguracao(
            "O secret DISCORD_CHANNEL_ID precisa ter só números: é o ID do canal "
            "(botão direito no canal → Copiar ID do canal), não o nome."
        )
    return token, canal
