"""Meme da Semana: conta os votos (😂) dos últimos dias, anuncia o pódio e mostra o termômetro.

Sai sozinho no dia e hora do config.yml (domingo às 21h). Para anunciar na hora:
python -m bot.postar --modo ranking
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .config import Config
from .discord_api import Discord, link_da_mensagem
from .historico import Historico
from .termometro import Termometro, numero_br
from .util import contar_reacao

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
    emoji: str | tuple[str, ...],
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
        emojis = (emoji,) if isinstance(emoji, str) else emoji
        votos = sum(contar_reacao(mensagem, item) for item in emojis)
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


def como_andou(variacao: float) -> str:
    if abs(variacao) < 0.05:
        return "ficou parada"
    if variacao > 0:
        return f"🌶️ subiu {numero_br(variacao)}"
    return f"🧊 desceu {numero_br(-variacao)}"


def resumo_do_termometro(termometro: Termometro, inicio: datetime, fontes=None) -> str:
    andou = como_andou(termometro.variacao_desde(inicio))
    linhas = [f"Régua: **{termometro.descrever_regua()}** ({andou} na semana)"]
    em_alta, em_baixa = termometro.fontes_em_destaque(fontes=fontes)
    if em_alta:
        linhas.append("Em alta: " + ", ".join(f"r/{fonte}" for fonte, _ in em_alta))
    if em_baixa:
        linhas.append("Em baixa: " + ", ".join(f"r/{fonte}" for fonte, _ in em_baixa))
    return "\n".join(linhas)


def montar_anuncio(
    colocados: list[Colocado],
    servidor_id: str,
    canal_id: str,
    emoji: str | tuple[str, ...],
    inicio: datetime,
    fim: datetime,
    pasta_estoque: Path,
    termometro: Termometro | None = None,
    fontes=None,
) -> tuple[dict, tuple | None]:
    emoji = emoji if isinstance(emoji, str) else " ou ".join(emoji)
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
        resumo = resumo_do_termometro(termometro, inicio, fontes)
        embed["fields"] = [{"name": "🌡️ Termômetro da galera", "value": resumo}]
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


def anunciar(
    discord: Discord,
    config: Config,
    historico: Historico,
    termometro: Termometro,
    canal_id: str,
    quando: datetime,
    log=print,
) -> list[Colocado]:
    """Conta os votos dos últimos dias, posta o anúncio e registra no histórico."""
    emoji = config.reacoes.votos_do_ranking()
    inicio = quando - timedelta(days=config.ranking_dias)
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
        quando,
        config.estoque_pasta,
        termometro,
        config.fontes,
    )
    mensagem = discord.enviar(canal_id, corpo, anexo)
    historico.registrar_ranking(mensagem["id"], quando)
    if colocados:
        log(f"🏆 Meme da Semana anunciado: {descrever(colocados[0])} com {colocados[0].votos} voto(s).")
    else:
        log("🏆 Meme da Semana anunciado (ninguém votou essa semana).")
    return colocados
