"""Apaga os memes do bot que a galera marcou como "passou do ponto" (🚫).

Roda toda vez que o bot acorda (de hora em hora). Antes de apagar, conta os votos do
meme no termômetro, para a régua não perder os 🚫 que levaram à remoção.
"""

from __future__ import annotations

from .config import Config
from .discord_api import Discord, ErroDiscord
from .historico import Historico
from .termometro import Termometro
from .util import contar_reacao


def moderar(
    discord: Discord,
    config: Config,
    historico: Historico,
    canal_id: str,
    log=print,
    mensagens: list[dict] | None = None,
    termometro: Termometro | None = None,
) -> list[dict]:
    """Confere as mensagens recentes do canal e apaga os memes do bot com 🚫 suficientes."""
    ids_dos_memes = historico.ids_de_mensagens()
    if not ids_dos_memes:
        return []
    if mensagens is None:
        mensagens = discord.mensagens(canal_id, limite=100)
    emoji = config.reacoes.passou_do_ponto
    removidos = []
    for mensagem in mensagens:
        if mensagem.get("id") not in ids_dos_memes:
            continue  # só mexe nos memes que o próprio bot postou
        votos = contar_reacao(mensagem, emoji)
        if votos < config.votos_para_remover:
            continue
        registro = historico.por_mensagem(mensagem["id"]) or {}
        if termometro is not None:
            termometro.contar_votos(mensagem, registro, config.reacoes)
        try:
            discord.apagar(canal_id, mensagem["id"])
        except ErroDiscord as erro:
            if erro.codigo == 10008:  # alguém já apagou
                continue
            raise
        origem = registro.get("link") or registro.get("chave") or mensagem["id"]
        log(f"{emoji} Meme removido pela galera ({votos} votos): {origem}")
        removidos.append(registro)
    return removidos
