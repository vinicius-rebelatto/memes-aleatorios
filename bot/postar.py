"""O bot de memes. O GitHub Actions acorda ele de hora em hora (e quando alguém aperta o botão).

Toda vez que acorda, o bot:
1. lê as reações dos memes recentes e atualiza o termômetro;
2. apaga o que passou do ponto;
3. posta um meme, se for hora (agenda do config.yml) e o daquele horário ainda não saiu;
4. anuncia o Meme da Semana, se for dia e hora.

Uso:
    python -m bot.postar --modo agenda    # o que o relógio faz: só posta se for hora
    python -m bot.postar --modo agora     # posta um meme agora (padrão do botão "Run workflow")
    python -m bot.postar --modo ranking   # anuncia o Meme da Semana agora
    python -m bot.postar --modo simular   # testa as fontes e mostra o próximo meme, sem Discord
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import requests

from .agenda import formatar, janela_aberta, proximo_horario, ranking_na_hora
from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .fontes import ErroDeFonte, Meme, buscar_memes, escolher_meme, titulo_util
from .historico import Historico
from .moderar import moderar
from .ranking import anunciar
from .termometro import DIAS_CONTANDO_VOTOS, Termometro, numero_br
from .util import agora, escrever_resumo

MODOS = ("agenda", "agora", "ranking", "simular")
COR_REDDIT = 0xFF4500
COR_ESTOQUE = 0x57F287
PAUSA_ENTRE_REACOES = 0.35  # o Discord limita reações muito seguidas


class SemMemeNovo(Exception):
    pass


@dataclass
class Resultado:
    meme: dict | None = None
    removidos: list[dict] = field(default_factory=list)
    ranking: bool = False
    erros: list[str] = field(default_factory=list)

    @property
    def mudou_algo(self) -> bool:
        return bool(self.meme or self.removidos or self.ranking)


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


def postar_meme(
    discord: Discord,
    config: Config,
    historico: Historico,
    termometro: Termometro,
    canal_id: str,
    permitir_nsfw: bool,
    quando: datetime,
    escolher=None,
    log=print,
) -> dict:
    """Escolhe um meme novo, posta com as 4 reações e registra no histórico."""
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
    return historico.registrar(meme, mensagem["id"], quando)


def hora_do_meme(config: Config, historico: Historico, quando: datetime, log=print) -> bool:
    inicio = janela_aberta(config.horarios, config.tolerancia, quando)
    if inicio is None:
        log(f"⏰ Fora do horário de posts. Próximo: {formatar(proximo_horario(config.horarios, quando))}.")
        return False
    if historico.postou_desde(inicio):
        log(f"✅ O meme das {formatar(inicio)} já saiu.")
        return False
    log(f"⏰ Hora do meme das {formatar(inicio)}.")
    return True


def executar(
    discord: Discord,
    config: Config,
    historico: Historico,
    termometro: Termometro,
    canal_id: str,
    modo: str = "agenda",
    quando: datetime | None = None,
    escolher=None,
    log=print,
) -> Resultado:
    """Uma "acordada" do bot. Erros do Discord no meio do caminho são anotados no resultado."""
    quando = quando or agora()
    resultado = Resultado()
    canal = discord.canal(canal_id)  # também confere se o bot enxerga o canal
    permitir_nsfw = config.permitir_nsfw and bool(canal.get("nsfw"))

    try:
        desde_ms = int((quando - timedelta(days=DIAS_CONTANDO_VOTOS)).timestamp() * 1000)
        mensagens = discord.mensagens_desde(canal_id, desde_ms)
        termometro.atualizar(mensagens, historico, config.reacoes, quando)
        resultado.removidos = moderar(
            discord, config, historico, canal_id, log, mensagens=mensagens, termometro=termometro
        )
    except ErroDiscord as erro:
        log(f"⚠️ Não consegui ler as reações agora: {erro}")
    log(f"🌡️ Régua: {termometro.descrever_regua()}")

    if modo == "agora" or (modo == "agenda" and hora_do_meme(config, historico, quando, log)):
        if config.permitir_nsfw and not permitir_nsfw:
            log("ℹ️ NSFW liberado no config, mas o canal não está marcado como restrito por idade: NSFW fica de fora.")
        try:
            resultado.meme = postar_meme(
                discord, config, historico, termometro, canal_id, permitir_nsfw, quando, escolher, log
            )
            log(f"✅ Meme postado! {descrever_origem(resultado.meme)}")
        except (SemMemeNovo, ErroDiscord) as erro:
            resultado.erros.append(str(erro))
            log(f"❌ {erro}")

    if modo == "ranking" or (
        modo == "agenda"
        and ranking_na_hora(
            config.ranking_dia, config.ranking_horario, config.tolerancia, quando, historico.ultimo_ranking()
        )
    ):
        try:
            anunciar(discord, config, historico, termometro, canal_id, quando, log)
            resultado.ranking = True
        except ErroDiscord as erro:
            resultado.erros.append(str(erro))
            log(f"❌ Meme da Semana: {erro}")
    return resultado


def descrever_origem(registro: dict) -> str:
    if registro.get("fonte") == "reddit":
        nsfw = " 🔞" if registro.get("nsfw") else ""
        return f"r/{registro.get('subreddit')}{nsfw} — {registro.get('link')}"
    return f"estoque — {registro.get('arquivo')}"


def diagnosticar_fontes(config: Config, termometro: Termometro, historico: Historico) -> None:
    """Mostra, para cada fonte, se a meme-api respondeu e quantos memes novos ela tem."""
    pesos = {fonte.subreddit: termometro.peso_da_fonte(fonte) for fonte in config.fontes}
    total = sum(pesos.values()) or 1
    print(f"🌡️ Régua: {termometro.descrever_regua()}")
    print(f"⏰ Horários: {', '.join(formatar(h) for h in config.horarios)}\n")
    print("Fonte                 nível  chance   memes  novos  nsfw")
    for fonte in config.fontes:
        chance = numero_br(100 * pesos[fonte.subreddit] / total) + "%"
        try:
            memes = buscar_memes(fonte.subreddit)
        except (requests.RequestException, ErroDeFonte, ValueError) as erro:
            print(f"r/{fonte.subreddit:<19} {numero_br(fonte.nivel):>5}  {chance:>6}  ❌ {erro}")
            continue
        novos = sum(1 for meme in memes if not historico.ja_postado(meme))
        nsfw = sum(1 for meme in memes if meme.nsfw)
        linha = f"{len(memes):>5}  {novos:>5}  {nsfw:>4}"
        print(f"r/{fonte.subreddit:<19} {numero_br(fonte.nivel):>5}  {chance:>6}  {linha}")
    print("\n(chance = probabilidade de cada fonte ser a primeira tentativa num post normal)\n")


def simular(config: Config, historico: Historico, termometro: Termometro) -> int:
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


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="O bot de memes do Discord.")
    parser.add_argument("--modo", choices=MODOS, default="agora", help="o que fazer (padrão: agora)")
    parser.add_argument("--simular", action="store_true", help="atalho para --modo simular")
    args = parser.parse_args(argumentos)
    modo = "simular" if args.simular else args.modo

    try:
        config = carregar_config()
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1
    historico = Historico.carregar(config.historico)
    termometro = Termometro.carregar(config.termometro, config.regua_inicial)

    if modo == "simular":
        return simular(config, historico, termometro)

    try:
        token, canal_id = ler_segredos()
    except SegredosAusentes as aviso:
        print(f"⚠️ {aviso}")
        escrever_resumo(f"⚠️ {aviso}")
        return 0
    except ErroDeConfiguracao as erro:
        print(f"❌ {erro}")
        return 1

    linhas: list[str] = []

    def log(texto: str) -> None:
        print(texto)
        linhas.append(texto)

    try:
        resultado = executar(Discord(token), config, historico, termometro, canal_id, modo, log=log)
    except ErroDiscord as erro:
        log(f"❌ {erro}")
        escrever_resumo("\n".join(f"- {linha}" for linha in linhas))
        return 1

    if resultado.mudou_algo:
        historico.salvar()
        termometro.salvar()
    escrever_resumo("\n".join(f"- {linha}" for linha in linhas))
    return 1 if resultado.erros else 0


if __name__ == "__main__":
    sys.exit(main())
