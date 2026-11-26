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
from pathlib import Path

import requests

from .agenda import descrever_horarios, formatar, janela_aberta, proximo_horario, ranking_na_hora
from .config import Config, ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos
from .discord_api import Discord, ErroDiscord
from .fontes import (
    EXTENSOES_DE_IMAGEM,
    ErroDeFonte,
    Meme,
    baixar_imagem,
    buscar_memes,
    candidatos_da_fonte,
    enviados_pelo_comando,
    escolher_meme,
    pontuar,
)
from .historico import Historico
from .moderar import moderar
from .painel import montar_painel, salvar_painel
from .ranking import anunciar
from .termometro import DIAS_CONTANDO_VOTOS, Termometro, numero_br
from .util import agora, escrever_resumo

MODOS = ("agenda", "agora", "ranking", "simular")
PAUSA_ENTRE_REACOES = 0.35  # o Discord limita reações muito seguidas
SEM_MENCOES = {"parse": []}


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


def nome_do_arquivo(meme: Meme) -> str:
    """meme.jpg, meme.png, meme.gif...: a extensão vem do arquivo ou do link da imagem."""
    origem = meme.arquivo.name if meme.arquivo else meme.imagem.split("?")[0]
    extensao = Path(origem).suffix.lower().replace(".jpeg", ".jpg")
    return "meme" + (extensao if extensao in EXTENSOES_DE_IMAGEM else ".jpg")


def mensagem_com_link(meme: Meme) -> dict:
    """Plano B: só o link da imagem, que o Discord também mostra como imagem."""
    return {"content": meme.imagem, "allowed_mentions": SEM_MENCOES}


def montar_mensagem(meme: Meme, baixar=None) -> tuple[dict, tuple | None]:
    """Só a imagem: sem moldura, título, link ou rodapé. Devolve (corpo, anexo).

    O meme vai como arquivo anexado, que o Discord mostra solto, só a imagem. Se não der
    para baixar a imagem do Reddit, vai o link dela.
    """
    nome = nome_do_arquivo(meme)
    conteudo = meme.arquivo.read_bytes() if meme.arquivo else (baixar or baixar_imagem)(meme.imagem)
    if conteudo is None:
        return mensagem_com_link(meme), None
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    corpo = {"attachments": [{"id": 0, "filename": nome}], "allowed_mentions": SEM_MENCOES}
    return corpo, (nome, conteudo, tipo)


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
    baixar=None,
) -> dict:
    """Escolhe um meme novo, posta só a imagem com as reações e registra no histórico."""
    if escolher is None:
        do_comando = enviados_pelo_comando(config.worker)

        def ja_saiu(meme: Meme) -> bool:
            return historico.ja_postado(meme) or meme.link in do_comando or meme.imagem in do_comando

        def escolher():
            return escolher_meme(config, ja_saiu, log=log, termometro=termometro, permitir_nsfw=permitir_nsfw)

    meme = escolher()
    if meme is None:
        raise SemMemeNovo(
            "Não achei nenhum meme novo: a meme-api falhou ou todos os memes recentes já saíram, "
            "e o estoque não tem meme novo."
        )
    corpo, anexo = montar_mensagem(meme, baixar)
    if anexo is None:
        log("ℹ️ Não consegui baixar a imagem do Reddit: mandei o link dela (o Discord mostra a imagem igual).")
    try:
        mensagem = discord.enviar(canal_id, corpo, anexo)
    except ErroDiscord as erro:
        grande_demais = erro.status == 413 or erro.codigo == 40005
        if anexo is None or not meme.imagem or not grande_demais:
            raise
        log("ℹ️ A imagem passou do limite de upload do servidor: mandei o link dela.")
        mensagem = discord.enviar(canal_id, mensagem_com_link(meme))
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
    baixar=None,
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
                discord, config, historico, termometro, canal_id, permitir_nsfw, quando, escolher, log, baixar
            )
            log(f"✅ Meme postado! {descrever_origem(resultado.meme)}")
        except SemMemeNovo as erro:
            if modo == "agenda":  # com muitos horários, faltar meme às vezes é normal: tenta no próximo
                log(f"⚠️ {erro} Tento de novo no próximo horário.")
            else:
                resultado.erros.append(str(erro))
                log(f"❌ {erro}")
        except ErroDiscord as erro:
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
    """Mostra, para cada fonte, se a meme-api respondeu, quantos memes novos ela tem e os melhores."""
    chances = termometro.chances(config.fontes, config.surpresa)
    print(f"🌡️ Régua: {termometro.descrever_regua()}")
    print(f"⏰ Horários: {descrever_horarios(config.horarios)}\n")
    categorias = termometro.chances_das_categorias(config.fontes, config.surpresa)
    print("Categorias: " + " · ".join(f"{nome} {numero_br(100 * chance)}%" for nome, chance in categorias.items()))
    print()
    print("Fonte                     nível  chance  memes  novos  nsfw  categoria")
    melhores: list[tuple[str, list[Meme]]] = []
    for fonte in config.fontes:
        nivel = numero_br(fonte.nivel) if fonte.segue_a_regua else "fora"
        inicio = f"r/{fonte.subreddit:<22}  {nivel:>5}  {numero_br(100 * chances[fonte.subreddit]) + '%':>6}"
        try:
            memes = buscar_memes(fonte.subreddit)
        except (requests.RequestException, ErroDeFonte, ValueError) as erro:
            print(f"{inicio}  ❌ {erro}")
            continue
        novos, id_mais_novo = candidatos_da_fonte(
            fonte, memes, historico.ja_postado, True, config.votos_minimos, config.bloquear
        )
        nsfw = sum(1 for meme in novos if meme.nsfw)
        print(f"{inicio}  {len(memes):>5}  {len(novos):>5}  {nsfw:>4}  {fonte.categoria}")
        novos.sort(key=lambda meme: -pontuar(meme, id_mais_novo))
        melhores.append((fonte.subreddit, novos[:3]))
    print("\n(memes = imagens que a meme-api trouxe; novos = inéditas, com menos de 60 dias e que passam nos filtros)")
    print("(nível fora = fora da régua; chance = de a fonte ser a primeira tentativa do próximo meme)\n")
    print("Os memes que cada fonte mandaria agora:")
    for subreddit, memes in melhores:
        for meme in memes:
            nsfw = " 🔞" if meme.nsfw else ""
            print(f"  r/{subreddit} ⬆️{meme.votos_reddit}{nsfw}: {meme.titulo[:80]} — {meme.link}")
    print()


def simular(config: Config, historico: Historico, termometro: Termometro) -> int:
    diagnosticar_fontes(config, termometro, historico)
    meme = escolher_meme(config, historico.ja_postado, termometro=termometro, permitir_nsfw=False)
    if meme is None:
        print("❌ Nenhum meme novo encontrado.")
        return 1
    corpo, anexo = montar_mensagem(meme)
    print("🧪 Simulação: este seria o próximo post (NSFW desligado na simulação)")
    origem = {"fonte": meme.fonte, "subreddit": meme.subreddit, "link": meme.link, "arquivo": meme.arquivo}
    print(f"   {descrever_origem(origem)}")
    if anexo:
        print(f"   📎 vai só a imagem, como arquivo ({len(anexo[1]) // 1024} KB)")
    else:
        print("   🔗 não consegui baixar a imagem: iria o link dela")
    print(json.dumps(corpo, ensure_ascii=False, indent=2))
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

    quando = agora()
    try:
        resultado = executar(Discord(token), config, historico, termometro, canal_id, modo, quando, log=log)
    except ErroDiscord as erro:
        log(f"❌ {erro}")
        escrever_resumo("\n".join(f"- {linha}" for linha in linhas))
        return 1

    if resultado.mudou_algo:
        historico.salvar()
        termometro.salvar()
    if resultado.mudou_algo or not config.painel.exists():
        salvar_painel(config.painel, montar_painel(config, termometro, historico, quando))
    escrever_resumo("\n".join(f"- {linha}" for linha in linhas))
    return 1 if resultado.erros else 0


if __name__ == "__main__":
    sys.exit(main())
