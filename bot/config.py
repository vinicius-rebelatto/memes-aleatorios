"""Lê o config.yml e os segredos (DISCORD_TOKEN e DISCORD_CHANNEL_ID)."""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time, timedelta
from pathlib import Path

import yaml

from .agenda import DIAS_DA_SEMANA

RAIZ = Path(__file__).resolve().parent.parent
CONFIG_PADRAO = RAIZ / "config.yml"
HORARIOS_PADRAO = (time(9), time(12), time(15), time(18), time(21))


class ErroDeConfiguracao(Exception):
    """Problema de configuração, com uma mensagem pensada para quem lê o log."""


class SegredosAusentes(ErroDeConfiguracao):
    """Nenhum segredo configurado ainda: o bot ainda não foi instalado."""


@dataclass(frozen=True)
class Fonte:
    subreddit: str
    nivel: float = 3.0  # 1 = leve ... 5 = pesado
    peso: float = 1.0


@dataclass(frozen=True)
class Reacoes:
    engracado: str = "😂"
    sem_graca: str = "😐"
    mais_pesado: str = "🌶️"
    passou_do_ponto: str = "🚫"

    def como_dict(self) -> dict[str, str]:
        return {
            "engracado": self.engracado,
            "sem_graca": self.sem_graca,
            "mais_pesado": self.mais_pesado,
            "passou_do_ponto": self.passou_do_ponto,
        }

    def em_ordem(self) -> tuple[str, ...]:
        return tuple(self.como_dict().values())


@dataclass(frozen=True)
class Config:
    fontes: tuple[Fonte, ...]
    reacoes: Reacoes = field(default_factory=Reacoes)
    votos_para_remover: int = 3
    regua_inicial: float = 3.0
    surpresa: float = 0.2
    permitir_nsfw: bool = True
    ranking_dias: int = 7
    ranking_quantidade: int = 3
    ranking_incluir_galera: bool = True
    estoque_pasta: Path = RAIZ / "estoque"
    estoque_chance: float = 0.2
    historico: Path = RAIZ / "dados" / "historico.json"
    termometro: Path = RAIZ / "dados" / "termometro.json"
    horarios: tuple[time, ...] = HORARIOS_PADRAO
    tolerancia: timedelta = timedelta(minutes=120)
    ranking_dia: int = 6  # 0 = segunda ... 6 = domingo
    ranking_horario: time = time(21)


def _horario(valor, nome: str) -> time:
    """Aceita "09:00", "9h", "21h30" e também o número que o YAML cria com 12:00 sem aspas."""
    if isinstance(valor, int) and not isinstance(valor, bool):
        horas, minutos = (valor, 0) if valor < 24 else divmod(valor, 60)
    else:
        texto = str(valor).strip().lower().replace("h", ":")
        partes = texto.split(":") + ["0"]
        try:
            horas, minutos = int(partes[0]), int(partes[1] or 0)
        except ValueError:
            raise ErroDeConfiguracao(f"No config.yml, '{nome}' precisa ser um horário como \"09:00\".") from None
    if not (0 <= horas < 24 and 0 <= minutos < 60):
        raise ErroDeConfiguracao(f"No config.yml, '{nome}' não é um horário válido ({valor}).")
    return time(horas, minutos)


def _dia_da_semana(valor) -> int:
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode().lower()
    texto = texto.replace("-feira", "").strip()
    if texto not in DIAS_DA_SEMANA:
        raise ErroDeConfiguracao(
            f"No config.yml, ranking.dia precisa ser um dia da semana, como 'domingo' (veio '{valor}')."
        )
    return DIAS_DA_SEMANA[texto]


def _ler_agenda(dados: dict) -> tuple[tuple[time, ...], timedelta]:
    agenda = _secao(dados, "agenda")
    lista = agenda.get("horarios", [h.strftime("%H:%M") for h in HORARIOS_PADRAO])
    if not isinstance(lista, list) or not lista:
        raise ErroDeConfiguracao('No config.yml, agenda.horarios precisa ser uma lista, como ["09:00", "12:00"].')
    horarios = tuple(sorted({_horario(item, "agenda.horarios") for item in lista}))
    minutos = _numero(agenda.get("tolerancia_minutos", 120), "agenda.tolerancia_minutos", int)
    if minutos < 1:
        raise ErroDeConfiguracao("agenda.tolerancia_minutos precisa ser pelo menos 1.")
    return horarios, timedelta(minutes=minutos)


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


def _fracao(valor, nome: str) -> float:
    numero = _numero(valor, nome)
    if not 0 <= numero <= 1:
        raise ErroDeConfiguracao(f"No config.yml, '{nome}' precisa estar entre 0 e 1 (ex.: 0.2 = 20%).")
    return numero


def _nivel(valor, nome: str) -> float:
    numero = _numero(valor, nome)
    if not 1 <= numero <= 5:
        raise ErroDeConfiguracao(f"No config.yml, '{nome}' precisa estar entre 1 (leve) e 5 (pesado).")
    return numero


def _ler_fontes(dados: dict) -> tuple[Fonte, ...]:
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
        fontes.append(Fonte(nome, _nivel(item.get("nivel", 3), f"nivel de r/{nome}"), peso))
    if not fontes:
        raise ErroDeConfiguracao("O config.yml precisa ter pelo menos uma fonte em 'fontes'.")
    return tuple(fontes)


def _ler_reacoes(dados: dict) -> Reacoes:
    secao = _secao(dados, "reacoes")
    padrao = Reacoes().como_dict()
    escolhidas = {nome: str(secao.get(nome, emoji)).strip() for nome, emoji in padrao.items()}
    if any(not emoji for emoji in escolhidas.values()):
        raise ErroDeConfiguracao("No config.yml, nenhuma das 4 reações pode ficar vazia.")
    if len(set(escolhidas.values())) != len(escolhidas):
        raise ErroDeConfiguracao("No config.yml, as 4 reações precisam ser emojis diferentes.")
    return Reacoes(**escolhidas)


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

    termometro = _secao(dados, "termometro")
    nsfw = _secao(dados, "nsfw")
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

    pasta = Path(str(estoque.get("pasta", "estoque")))
    if not pasta.is_absolute():
        pasta = caminho.parent / pasta
    horarios, tolerancia = _ler_agenda(dados)

    return Config(
        horarios=horarios,
        tolerancia=tolerancia,
        ranking_dia=_dia_da_semana(ranking.get("dia", "domingo")),
        ranking_horario=_horario(ranking.get("horario", "21:00"), "ranking.horario"),
        fontes=_ler_fontes(dados),
        reacoes=_ler_reacoes(dados),
        votos_para_remover=votos_para_remover,
        regua_inicial=_nivel(termometro.get("regua_inicial", 3), "termometro.regua_inicial"),
        surpresa=_fracao(termometro.get("surpresa", 0.2), "termometro.surpresa"),
        permitir_nsfw=bool(nsfw.get("permitir", True)),
        ranking_dias=dias,
        ranking_quantidade=quantidade,
        ranking_incluir_galera=bool(ranking.get("incluir_posts_da_galera", True)),
        estoque_pasta=pasta,
        estoque_chance=_fracao(estoque.get("chance", 0.2), "estoque.chance"),
        historico=caminho.parent / "dados" / "historico.json",
        termometro=caminho.parent / "dados" / "termometro.json",
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
            "(passo 4 do README). Nada foi feito."
        )
    faltando = [nome for nome, valor in (("DISCORD_TOKEN", token), ("DISCORD_CHANNEL_ID", canal)) if not valor]
    if faltando:
        raise ErroDeConfiguracao(f"Falta configurar o secret {' e '.join(faltando)} no GitHub (passo 4 do README).")
    if not canal.isdigit():
        raise ErroDeConfiguracao(
            "O secret DISCORD_CHANNEL_ID precisa ter só números: é o ID do canal "
            "(botão direito no canal → Copiar ID do canal), não o nome."
        )
    return token, canal
