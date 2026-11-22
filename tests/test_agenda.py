from datetime import date, datetime, time, timedelta, timezone

import pytest

from bot.agenda import formatar, janela_aberta, proximo_horario, ranking_na_hora

BRT = timezone(timedelta(hours=-3))
HORARIOS = (time(9), time(12), time(15), time(18), time(21))
DUAS_HORAS = timedelta(hours=2)


def em(hora: int, minuto: int = 0, dia: int = 22) -> datetime:
    return datetime(2026, 11, dia, hora, minuto, tzinfo=BRT)  # 22/11/2026 é domingo


@pytest.mark.parametrize(
    ("agora", "esperado"),
    [
        (em(9, 0), em(9)),  # em cima da hora
        (em(9, 1), em(9)),
        (em(10, 59), em(9)),  # atrasado, mas dentro das 2h de tolerância
        (em(11, 0), None),  # passou da tolerância: pula o das 9h
        (em(12, 30), em(12)),
        (em(21, 40), em(21)),
        (em(23, 5), None),  # noite: nada
        (em(3, 46), None),  # madrugada: nada (o post das 3h46 de ontem não aconteceria)
        (em(8, 59), None),
    ],
)
def test_janela_aberta(agora, esperado):
    assert janela_aberta(HORARIOS, DUAS_HORAS, agora) == esperado


def test_janela_termina_no_proximo_horario_se_a_tolerancia_for_grande():
    assert janela_aberta(HORARIOS, timedelta(hours=5), em(12, 30)) == em(12)
    assert janela_aberta(HORARIOS, timedelta(hours=5), em(14, 59)) == em(12)


def test_janela_que_atravessa_a_meia_noite():
    assert janela_aberta((time(23),), DUAS_HORAS, em(0, 30, dia=23)) == em(23, dia=22)


def test_proximo_horario():
    assert proximo_horario(HORARIOS, em(10)) == em(12)
    assert proximo_horario(HORARIOS, em(22)) == em(9, dia=23)
    assert proximo_horario(HORARIOS, em(12)) == em(15)  # exatamente no horário: o próximo é o seguinte


def test_ranking_no_domingo_as_21h_uma_vez_so():
    domingo = 6
    assert ranking_na_hora(domingo, time(21), DUAS_HORAS, em(21, 10), ultimo=None)
    assert ranking_na_hora(domingo, time(21), DUAS_HORAS, em(21, 10), ultimo=date(2026, 11, 15))
    assert not ranking_na_hora(domingo, time(21), DUAS_HORAS, em(21, 10), ultimo=date(2026, 11, 22))  # já saiu
    assert not ranking_na_hora(domingo, time(21), DUAS_HORAS, em(20, 59), ultimo=None)  # cedo
    assert not ranking_na_hora(domingo, time(21), DUAS_HORAS, em(23, 30), ultimo=None)  # tarde demais
    assert not ranking_na_hora(domingo, time(21), DUAS_HORAS, em(21, 10, dia=23), ultimo=None)  # segunda


def test_formatar():
    assert formatar(em(9)) == "9h"
    assert formatar(time(21, 30)) == "21h30"
