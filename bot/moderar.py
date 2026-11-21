"""Apaga os memes do bot que a galera marcou como "passou do ponto" (🚫).

Roda sozinho de hora em hora e também antes de cada post.
Uso manual: python -m bot.moderar
"""

from __future__ import annotations

import sys

from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .historico import Historico
from .util import contar_reacao, escrever_resumo


def moderar(discord: Discord, config: Config, historico: Historico, canal_id: str, log=print) -> list[dict]:
    """Confere as últimas 100 mensagens do canal e apaga os memes do bot com 🚫 suficientes."""
    ids_dos_memes = historico.ids_de_mensagens()
    if not ids_dos_memes:
        return []
    removidos = []
    for mensagem in discord.mensagens(canal_id, limite=100):
        if mensagem.get("id") not in ids_dos_memes:
            continue  # só mexe nos memes que o próprio bot postou
        votos = contar_reacao(mensagem, config.emoji_remover)
        if votos < config.votos_para_remover:
            continue
        try:
            discord.apagar(canal_id, mensagem["id"])
        except ErroDiscord as erro:
            if erro.codigo == 10008:  # alguém já apagou
                continue
            raise
        registro = historico.por_mensagem(mensagem["id"]) or {}
        origem = registro.get("link") or registro.get("chave") or mensagem["id"]
        log(f"{config.emoji_remover} Meme removido pela galera ({votos} votos): {origem}")
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
    try:
        removidos = moderar(Discord(token), config, historico, canal_id)
    except ErroDiscord as erro:
        print(f"❌ {erro}")
        escrever_resumo(f"❌ {erro}")
        return 1

    if removidos:
        escrever_resumo(f"### {config.emoji_remover} {len(removidos)} meme(s) removido(s) pela galera")
    else:
        print("✅ Nenhum meme passou do ponto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
