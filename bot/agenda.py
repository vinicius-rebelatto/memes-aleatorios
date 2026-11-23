"""Quando o bot posta: os horários dos memes e o dia do Meme da Semana.

O agendador do GitHub anda atrasando as execuções em horas. Por isso o bot não confia
no horário em que foi acordado: a cada execução ele confere se está dentro da "janela"
de algum horário (o horário + a tolerância) e se o meme daquela janela já saiu.
Assim ele nunca posta de madrugada nem posta duas vezes no mesmo horário, não importa
quantas vezes nem quando for acordado.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

DIAS_DA_SEMANA = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}


def _no_dia(dia: date, horario: time, fuso) -> datetime:
    return datetime.combine(dia, horario, tzinfo=fuso)


def _horarios_em_volta(horarios: Iterable[time], agora: datetime, dias: tuple[int, ...]) -> list[datetime]:
    return sorted(
        _no_dia(agora.date() + timedelta(days=deslocamento), horario, agora.tzinfo)
        for deslocamento in dias
        for horario in horarios
    )


def janela_aberta(horarios: Iterable[time], tolerancia: timedelta, agora: datetime) -> datetime | None:
    """O horário de post cuja janela está aberta agora, ou None se não estiver em nenhuma.

    A janela vai do horário até a tolerância, ou até o próximo horário, o que vier primeiro.
    """
    candidatos = _horarios_em_volta(horarios, agora, (-1, 0, 1))
    passados = [momento for momento in candidatos if momento <= agora]
    if not passados:
        return None
    inicio = passados[-1]
    seguintes = [momento for momento in candidatos if momento > inicio]
    fim = min([inicio + tolerancia, *seguintes[:1]])
    return inicio if agora < fim else None


def proximo_horario(horarios: Iterable[time], agora: datetime) -> datetime:
    return next(momento for momento in _horarios_em_volta(horarios, agora, (0, 1)) if momento > agora)


def ranking_na_hora(
    dia_da_semana: int, horario: time, tolerancia: timedelta, agora: datetime, ultimo: date | None
) -> bool:
    """True se é dia e hora do Meme da Semana e ele ainda não saiu hoje."""
    if agora.weekday() != dia_da_semana or ultimo == agora.date():
        return False
    inicio = _no_dia(agora.date(), horario, agora.tzinfo)
    return inicio <= agora < inicio + tolerancia


def formatar(momento: datetime | time) -> str:
    """Ex.: 9h, 21h30."""
    return f"{momento.hour}h{momento.minute:02d}" if momento.minute else f"{momento.hour}h"


def descrever_horarios(horarios: Iterable[time]) -> str:
    """Ex.: "de hora em hora, das 9h às 2h" ou "9h, 12h30, 20h" quando não há um ritmo fixo."""
    minutos = sorted({h.hour * 60 + h.minute for h in horarios})
    quantidade = len(minutos)
    if quantidade < 3:
        return ", ".join(formatar(time(m // 60, m % 60)) for m in minutos)
    # o "dia" do bot começa depois do maior intervalo sem posts (ex.: 9h..2h começa às 9h)
    intervalos = [((minutos[(i + 1) % quantidade] - minutos[i]) % 1440, i) for i in range(quantidade)]
    _, fim_do_dia = max(intervalos)
    ordem = minutos[fim_do_dia + 1 :] + minutos[: fim_do_dia + 1]
    textos = [formatar(time(m // 60, m % 60)) for m in ordem]
    passos = {(ordem[i + 1] - ordem[i]) % 1440 for i in range(quantidade - 1)}
    if len(passos) != 1:
        return ", ".join(textos)
    passo = passos.pop()
    if passo == 60:
        ritmo = "de hora em hora"
    elif passo % 60 == 0:
        ritmo = f"de {passo // 60} em {passo // 60} horas"
    else:
        ritmo = f"a cada {passo} minutos"
    return f"{ritmo}, das {textos[0]} às {textos[-1]}"
