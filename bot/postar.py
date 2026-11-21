"""Escolhe um meme novo e posta no canal (o GitHub Actions roda isto 3 vezes por dia).

Uso manual:
    python -m bot.postar             # posta de verdade (precisa dos secrets)
    python -m bot.postar --simular   # só mostra qual meme seria postado, sem Discord
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys

from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .fontes import Meme, escolher_meme, titulo_util
from .historico import Historico
from .moderar import moderar
from .util import agora, escrever_resumo

COR_REDDIT = 0xFF4500
COR_ESTOQUE = 0x57F287


class SemMemeNovo(Exception):
    pass


def montar_mensagem(meme: Meme, config: Config) -> tuple[dict, tuple | None]:
    """Monta a mensagem do Discord. Devolve (corpo, anexo); o anexo só existe para memes do estoque."""
    rodape = f"{config.emoji_voto} vota no Meme da Semana • {config.emoji_remover} passou do ponto"
    if meme.fonte == "reddit":
        embed = {
            "color": COR_REDDIT,
            "author": {"name": f"r/{meme.subreddit}", "url": meme.link},
            "image": {"url": meme.imagem},
            "footer": {"text": f"⬆️ {meme.votos_reddit} no Reddit • {rodape}"},
        }
        titulo = titulo_util(meme.titulo, meme.subreddit)
        if titulo:
            embed["title"] = titulo
            embed["url"] = meme.link
        return {"embeds": [embed], "allowed_mentions": {"parse": []}}, None

    nome = "meme" + meme.arquivo.suffix.lower()
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    embed = {
        "color": COR_ESTOQUE,
        "author": {"name": "📦 Estoque da galera"},
        "image": {"url": f"attachment://{nome}"},
        "footer": {"text": rodape},
    }
    corpo = {"embeds": [embed], "attachments": [{"id": 0, "filename": nome}], "allowed_mentions": {"parse": []}}
    return corpo, (nome, meme.arquivo.read_bytes(), tipo)


def postar(discord: Discord, config: Config, historico: Historico, canal_id: str, escolher=None, log=print) -> dict:
    """Modera os memes anteriores, escolhe um meme novo, posta, reage e registra no histórico."""
    escolher = escolher or (lambda: escolher_meme(config, historico.ja_postado, log=log))
    discord.canal(canal_id)  # confere se o bot enxerga o canal antes de tudo
    try:
        moderar(discord, config, historico, canal_id, log)
    except ErroDiscord as erro:
        log(f"⚠️ Não consegui moderar agora (sigo com o post): {erro}")

    meme = escolher()
    if meme is None:
        raise SemMemeNovo(
            "Não achei nenhum meme novo: a meme-api falhou ou todos os memes recentes já saíram, "
            "e o estoque não tem meme novo."
        )
    corpo, anexo = montar_mensagem(meme, config)
    mensagem = discord.enviar(canal_id, corpo, anexo)
    for posicao, emoji in enumerate((config.emoji_voto, config.emoji_remover)):
        if posicao:
            discord.dormir(0.3)  # o Discord limita reações muito seguidas
        try:
            discord.reagir(canal_id, mensagem["id"], emoji)
        except ErroDiscord as erro:
            log(f"⚠️ Não consegui reagir com {emoji}: {erro}")
    return historico.registrar(meme, mensagem["id"], agora())


def descrever_origem(registro: dict) -> str:
    if registro.get("fonte") == "reddit":
        return f"r/{registro.get('subreddit')} — {registro.get('link')}"
    return f"estoque — {registro.get('arquivo')}"


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Posta um meme no canal do Discord.")
    parser.add_argument("--simular", action="store_true", help="só mostra o meme escolhido, sem postar")
    args = parser.parse_args(argumentos)

    try:
        config = carregar_config()
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1
    historico = Historico.carregar(config.historico)

    if args.simular:
        meme = escolher_meme(config, historico.ja_postado)
        if meme is None:
            print("❌ Nenhum meme novo encontrado.")
            return 1
        corpo, anexo = montar_mensagem(meme, config)
        print("🧪 Simulação: este seria o próximo post")
        print(json.dumps(corpo, ensure_ascii=False, indent=2))
        if anexo:
            print(f"(com o arquivo {meme.arquivo})")
        return 0

    try:
        token, canal_id = ler_segredos()
    except SegredosAusentes as aviso:
        print(f"⚠️ {aviso}")
        escrever_resumo(f"⚠️ {aviso}")
        return 0
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1

    try:
        registro = postar(Discord(token), config, historico, canal_id)
    except (ErroDiscord, SemMemeNovo) as erro:
        print(f"❌ {erro}")
        escrever_resumo(f"❌ {erro}")
        return 1

    historico.salvar()
    print(f"✅ Meme postado! {descrever_origem(registro)}")
    escrever_resumo(f"### ✅ Meme postado\n{descrever_origem(registro)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
