"""Meme da Semana: conta os votos (😂) dos últimos dias, anuncia o pódio e mostra o termômetro.

Roda sozinho no domingo à noite.
Uso manual: python -m bot.ranking
"""

from __future__ import annotations

import mimetypes
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .config import ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord, link_da_mensagem
from .historico import Historico
from .termometro import Termometro, numero_br
from .util import agora, contar_reacao, escrever_resumo

MEDALHAS = ("🥇", "🥈", "🥉")
TIPOS_NORMAIS = (0, 19)  # 0 = mensagem comum, 19 = resposta a outra mensagem
COR_RANKING = 0xF1C40F


@dataclass
class Colocado:
    mensagem_id: str
    votos: int
    autor_id: str
    registro: dict | None = None  # preenchido quando é um meme postado pelo bot


def calcular_ranking(
    mensagens: list[dict],
    bot_id: str,
    historico: Historico,
    emoji: str,
    incluir_galera: bool = True,
    quantidade: int = 3,
) -> list[Colocado]:
    colocados = []
    for mensagem in mensagens:
        if mensagem.get("type", 0) not in TIPOS_NORMAIS:
            continue
        autor = mensagem.get("author") or {}
        registro = None
        if autor.get("id") == bot_id:
            registro = historico.por_mensagem(mensagem["id"])
            if registro is None:
                continue  # anúncios do próprio bot não concorrem
        elif not incluir_galera or autor.get("bot"):
            continue
        votos = contar_reacao(mensagem, emoji)
        if votos > 0:
            colocados.append(Colocado(mensagem["id"], votos, str(autor.get("id", "")), registro))
    # mais votos primeiro; no empate, ganha quem postou antes
    colocados.sort(key=lambda c: (-c.votos, int(c.mensagem_id)))
    return colocados[:quantidade]


def descrever(colocado: Colocado) -> str:
    registro = colocado.registro
    if registro is None:
        return f"meme de <@{colocado.autor_id}>"
    if registro.get("fonte") == "reddit":
        return f"meme do r/{registro.get('subreddit', 'reddit')}"
    return "meme do estoque da galera"


def resumo_do_termometro(termometro: Termometro, inicio: datetime) -> str:
    variacao = termometro.variacao_desde(inicio)
    if abs(variacao) < 0.05:
        andou = "ficou parada"
    elif variacao > 0:
        andou = f"🌶️ subiu {numero_br(variacao)}"
    else:
        andou = f"🧊 desceu {numero_br(-variacao)}"
    linhas = [f"Régua: **{termometro.descrever_regua()}** ({andou} na semana)"]
    em_alta, em_baixa = termometro.fontes_em_destaque()
    if em_alta:
        linhas.append("Em alta: " + ", ".join(f"r/{fonte}" for fonte, _ in em_alta))
    if em_baixa:
        linhas.append("Em baixa: " + ", ".join(f"r/{fonte}" for fonte, _ in em_baixa))
    return "\n".join(linhas)


def montar_anuncio(
    colocados: list[Colocado],
    servidor_id: str,
    canal_id: str,
    emoji: str,
    inicio: datetime,
    fim: datetime,
    pasta_estoque: Path,
    termometro: Termometro | None = None,
) -> tuple[dict, tuple | None]:
    if colocados:
        linhas = []
        for posicao, colocado in enumerate(colocados):
            medalha = MEDALHAS[posicao] if posicao < len(MEDALHAS) else f"{posicao + 1}º"
            link = link_da_mensagem(servidor_id, canal_id, colocado.mensagem_id)
            votos = "1 voto" if colocado.votos == 1 else f"{colocado.votos} votos"
            linhas.append(f"{medalha} **{votos}** — [{descrever(colocado)}]({link})")
        descricao = "\n".join(linhas)
    else:
        descricao = f"Ninguém votou essa semana 😢 Reajam com {emoji} nos memes que vocês curtirem!"

    embed = {
        "title": "🏆 Meme da Semana",
        "description": descricao,
        "color": COR_RANKING,
        "footer": {"text": f"Votação de {inicio:%d/%m} a {fim:%d/%m} • vote com {emoji} nos memes da semana"},
    }
    if termometro is not None:
        embed["fields"] = [{"name": "🌡️ Termômetro da galera", "value": resumo_do_termometro(termometro, inicio)}]
    corpo = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    anexo = None

    vencedor = (colocados[0].registro or {}) if colocados else {}
    if vencedor.get("fonte") == "reddit" and vencedor.get("imagem"):
        embed["image"] = {"url": vencedor["imagem"]}
    elif vencedor.get("fonte") == "estoque" and vencedor.get("arquivo"):
        arquivo = pasta_estoque / vencedor["arquivo"]
        if arquivo.is_file():
            nome = "vencedor" + arquivo.suffix.lower()
            tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
            embed["image"] = {"url": f"attachment://{nome}"}
            corpo["attachments"] = [{"id": 0, "filename": nome}]
            anexo = (nome, arquivo.read_bytes(), tipo)
    return corpo, anexo


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

    discord = Discord(token)
    historico = Historico.carregar(config.historico)
    termometro = Termometro.carregar(config.termometro, config.regua_inicial)
    emoji = config.reacoes.engracado
    fim = agora()
    inicio = fim - timedelta(days=config.ranking_dias)
    try:
        canal = discord.canal(canal_id)
        bot_id = discord.eu()["id"]
        mensagens = discord.mensagens_desde(canal_id, int(inicio.timestamp() * 1000))
        colocados = calcular_ranking(
            mensagens, bot_id, historico, emoji, config.ranking_incluir_galera, config.ranking_quantidade
        )
        corpo, anexo = montar_anuncio(
            colocados,
            str(canal.get("guild_id", "@me")),
            canal_id,
            emoji,
            inicio,
            fim,
            config.estoque_pasta,
            termometro,
        )
        discord.enviar(canal_id, corpo, anexo)
    except ErroDiscord as erro:
        print(f"❌ {erro}")
        escrever_resumo(f"❌ {erro}")
        return 1

    if colocados:
        vencedor = colocados[0]
        print(f"🏆 Meme da Semana anunciado: {descrever(vencedor)} com {vencedor.votos} voto(s).")
        escrever_resumo(f"### 🏆 Meme da Semana\n{descrever(vencedor)} venceu com {vencedor.votos} voto(s).")
    else:
        print("ℹ️ Ninguém votou essa semana; anúncio enviado mesmo assim.")
    print(f"🌡️ Régua: {termometro.descrever_regua()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
