"""Escolhe um meme novo e posta no canal (o GitHub Actions roda isto 3 vezes por dia).

A cada execução o bot: lê as reações dos memes recentes e atualiza o termômetro,
apaga o que passou do ponto, escolhe o próximo meme e posta com as 4 reações.

Uso manual:
    python -m bot.postar             # posta de verdade (precisa dos secrets)
    python -m bot.postar --simular   # testa as fontes e mostra o meme escolhido, sem Discord
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import timedelta

import requests

from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .fontes import ErroDeFonte, Meme, buscar_memes, escolher_meme, titulo_util
from .historico import Historico
from .moderar import moderar
from .termometro import DIAS_CONTANDO_VOTOS, Termometro, numero_br
from .util import agora, escrever_resumo

COR_REDDIT = 0xFF4500
COR_ESTOQUE = 0x57F287
PAUSA_ENTRE_REACOES = 0.35  # o Discord limita reações muito seguidas


class SemMemeNovo(Exception):
    pass


def legenda_das_reacoes(config: Config) -> str:
    r = config.reacoes
    return (
        f"{r.engracado} engraçado · {r.sem_graca} sem graça · "
        f"{r.mais_pesado} mais pesado · {r.passou_do_ponto} passou do ponto"
    )


def montar_mensagem(meme: Meme, config: Config, regua: float | None = None) -> tuple[dict, tuple | None]:
    """Monta a mensagem do Discord. Devolve (corpo, anexo); o anexo só existe para memes do estoque."""
    partes_do_rodape = []
    if meme.fonte == "reddit":
        partes_do_rodape.append(f"⬆️ {meme.votos_reddit} no Reddit")
    if regua is not None:
        partes_do_rodape.append(f"🌡️ régua {numero_br(regua)}/5")
    partes_do_rodape.append(legenda_das_reacoes(config))
    rodape = {"text": " • ".join(partes_do_rodape)}

    if meme.fonte == "reddit":
        nome_da_fonte = f"r/{meme.subreddit}"
        if meme.nsfw:
            nome_da_fonte = f"🔞 {nome_da_fonte}"
        embed = {
            "color": COR_REDDIT,
            "author": {"name": nome_da_fonte, "url": meme.link},
            "image": {"url": meme.imagem},
            "footer": rodape,
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
        "footer": rodape,
    }
    corpo = {"embeds": [embed], "attachments": [{"id": 0, "filename": nome}], "allowed_mentions": {"parse": []}}
    return corpo, (nome, meme.arquivo.read_bytes(), tipo)


def postar(
    discord: Discord,
    config: Config,
    historico: Historico,
    termometro: Termometro,
    canal_id: str,
    escolher=None,
    log=print,
) -> dict:
    """Atualiza o termômetro, modera, escolhe um meme novo, posta, reage e registra no histórico."""
    canal = discord.canal(canal_id)  # também confere se o bot enxerga o canal
    permitir_nsfw = config.permitir_nsfw and bool(canal.get("nsfw"))
    if config.permitir_nsfw and not permitir_nsfw:
        log("ℹ️ NSFW está liberado no config, mas o canal não está marcado como restrito por idade: NSFW fica de fora.")

    quando = agora()
    try:
        desde_ms = int((quando - timedelta(days=DIAS_CONTANDO_VOTOS)).timestamp() * 1000)
        mensagens = discord.mensagens_desde(canal_id, desde_ms)
        termometro.atualizar(mensagens, historico, config.reacoes, quando)
        moderar(discord, config, historico, canal_id, log, mensagens=mensagens, termometro=termometro)
    except ErroDiscord as erro:
        log(f"⚠️ Não consegui ler as reações agora (sigo com o post): {erro}")
    log(f"🌡️ Régua: {termometro.descrever_regua()}")

    escolher = escolher or (
        lambda: escolher_meme(config, historico.ja_postado, log=log, termometro=termometro, permitir_nsfw=permitir_nsfw)
    )
    meme = escolher()
    if meme is None:
        raise SemMemeNovo(
            "Não achei nenhum meme novo: a meme-api falhou ou todos os memes recentes já saíram, "
            "e o estoque não tem meme novo."
        )
    corpo, anexo = montar_mensagem(meme, config, termometro.regua)
    mensagem = discord.enviar(canal_id, corpo, anexo)
    for posicao, emoji in enumerate(config.reacoes.em_ordem()):
        if posicao:
            discord.dormir(PAUSA_ENTRE_REACOES)
        try:
            discord.reagir(canal_id, mensagem["id"], emoji)
        except ErroDiscord as erro:
            log(f"⚠️ Não consegui reagir com {emoji}: {erro}")
    return historico.registrar(meme, mensagem["id"], agora())


def descrever_origem(registro: dict) -> str:
    if registro.get("fonte") == "reddit":
        nsfw = " 🔞" if registro.get("nsfw") else ""
        return f"r/{registro.get('subreddit')}{nsfw} — {registro.get('link')}"
    return f"estoque — {registro.get('arquivo')}"


def diagnosticar_fontes(config: Config, termometro: Termometro, historico: Historico) -> None:
    """Mostra, para cada fonte, se a meme-api respondeu e quantos memes novos ela tem."""
    pesos = {fonte.subreddit: termometro.peso_da_fonte(fonte) for fonte in config.fontes}
    total = sum(pesos.values()) or 1
    print(f"🌡️ Régua: {termometro.descrever_regua()}\n")
    print("Fonte                 nível  chance   memes  novos  nsfw")
    for fonte in config.fontes:
        chance = f"{100 * pesos[fonte.subreddit] / total:5.1f}%"
        try:
            memes = buscar_memes(fonte.subreddit)
        except (requests.RequestException, ErroDeFonte, ValueError) as erro:
            print(f"r/{fonte.subreddit:<19} {numero_br(fonte.nivel):>5}  {chance}  ❌ {erro}")
            continue
        novos = sum(1 for meme in memes if not historico.ja_postado(meme))
        nsfw = sum(1 for meme in memes if meme.nsfw)
        print(f"r/{fonte.subreddit:<19} {numero_br(fonte.nivel):>5}  {chance}  {len(memes):>5}  {novos:>5}  {nsfw:>4}")
    print("\n(chance = probabilidade de cada fonte ser a primeira tentativa num post normal)\n")


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Posta um meme no canal do Discord.")
    parser.add_argument("--simular", action="store_true", help="testa as fontes e mostra o meme escolhido")
    args = parser.parse_args(argumentos)

    try:
        config = carregar_config()
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1
    historico = Historico.carregar(config.historico)
    termometro = Termometro.carregar(config.termometro, config.regua_inicial)

    if args.simular:
        diagnosticar_fontes(config, termometro, historico)
        meme = escolher_meme(config, historico.ja_postado, termometro=termometro, permitir_nsfw=False)
        if meme is None:
            print("❌ Nenhum meme novo encontrado.")
            return 1
        corpo, anexo = montar_mensagem(meme, config, termometro.regua)
        print("🧪 Simulação: este seria o próximo post (NSFW desligado na simulação)")
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
        registro = postar(Discord(token), config, historico, termometro, canal_id)
    except (ErroDiscord, SemMemeNovo) as erro:
        print(f"❌ {erro}")
        escrever_resumo(f"❌ {erro}")
        termometro.salvar()  # os votos lidos antes da falha continuam valendo
        return 1

    historico.salvar()
    termometro.salvar()
    print(f"✅ Meme postado! {descrever_origem(registro)}")
    escrever_resumo(f"### ✅ Meme postado\n{descrever_origem(registro)}\n\n🌡️ Régua: {termometro.descrever_regua()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
