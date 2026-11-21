"""Funções pequenas usadas em vários lugares do bot."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    FUSO = ZoneInfo("America/Sao_Paulo")
except Exception:  # sem base de fusos no sistema: Brasília é UTC-3 o ano todo
    FUSO = timezone(timedelta(hours=-3), "BRT")


def agora() -> datetime:
    """Data e hora atuais no horário de Brasília."""
    return datetime.now(FUSO)


def escrever_resumo(texto: str) -> None:
    """Escreve no resumo da execução do GitHub Actions (aparece na página da execução)."""
    caminho = os.environ.get("GITHUB_STEP_SUMMARY")
    if caminho:
        with open(caminho, "a", encoding="utf-8") as arquivo:
            arquivo.write(texto.rstrip() + "\n")


def mesmo_emoji(a: str | None, b: str | None) -> bool:
    """Compara emojis ignorando o 'seletor de variação' invisível (U+FE0F)."""
    if not a or not b:
        return False
    return a.replace("️", "") == b.replace("️", "")


def contar_reacao(mensagem: dict, emoji: str) -> int:
    """Quantas pessoas reagiram à mensagem com esse emoji, sem contar o próprio bot."""
    for reacao in mensagem.get("reactions") or []:
        if mesmo_emoji((reacao.get("emoji") or {}).get("name"), emoji):
            total = int(reacao.get("count") or 0)
            if reacao.get("me"):
                total -= 1
            return max(total, 0)
    return 0
