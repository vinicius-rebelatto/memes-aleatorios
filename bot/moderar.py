"""Apaga os memes do bot que a galera marcou como "passou do ponto" (🚫).

Roda sozinho de hora em hora e também antes de cada post. Antes de apagar, conta os
votos do meme no termômetro, para a régua não perder os 🚫 que levaram à remoção.
Uso manual: python -m bot.moderar
"""

from __future__ import annotations

import sys

from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .historico import Historico
from .termometro import Termometro
from .util import contar_reacao, escrever_resumo


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


def main() -> int:
    try:
        config = carregar_config()
        token, canal_id = ler_segredos()
    except SegredosAusentes as aviso:
        print(f"⚠️ {aviso}")
        escrever_resumo(f"⚠️ {aviso}")
        return 0
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1

    historico = Historico.carregar(config.historico)
    if not historico.ids_de_mensagens():
        print("ℹ️ Nenhum meme postado ainda, nada para moderar.")
        return 0
    termometro = Termometro.carregar(config.termometro, config.regua_inicial)
    try:
        removidos = moderar(Discord(token), config, historico, canal_id, termometro=termometro)
    except ErroDiscord as erro:
        print(f"❌ {erro}")
        escrever_resumo(f"❌ {erro}")
        return 1

    if removidos:
        termometro.salvar()
        print(f"🌡️ Régua agora: {termometro.descrever_regua()}")
        escrever_resumo(f"### {config.reacoes.passou_do_ponto} {len(removidos)} meme(s) removido(s) pela galera")
    else:
        print("✅ Nenhum meme passou do ponto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
