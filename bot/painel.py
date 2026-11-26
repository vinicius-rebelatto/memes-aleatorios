"""O painel: um resumo do termômetro para os comandos do Discord (/termometro e /meme).

Fica em dados/painel.json e é salvo junto com o histórico, a cada post. O Worker da
Cloudflare (pasta worker/) lê este arquivo direto do GitHub, então os comandos sempre
usam as fontes do config.yml e a régua mais recente, sem configurar nada lá.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from .agenda import descrever_horarios, formatar
from .config import Config
from .historico import Historico
from .ranking import como_andou
from .termometro import Termometro

DIAS_SEM_REPETIR = 3  # o /meme evita os memes que o bot mandou nesses últimos dias
NOMES_DOS_DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def montar_painel(config: Config, termometro: Termometro, historico: Historico, quando: datetime) -> dict:
    chances = termometro.chances(config.fontes, config.surpresa)
    em_alta, em_baixa = termometro.fontes_em_destaque(fontes=config.fontes)
    variacao = termometro.variacao_desde(quando - timedelta(days=7))
    fontes = sorted(config.fontes, key=lambda fonte: -chances[fonte.subreddit])
    return {
        "atualizado_em": quando.isoformat(timespec="seconds"),
        "regua": round(termometro.regua, 2),
        "regua_texto": termometro.descrever_regua(),
        "regua_na_semana": como_andou(variacao),
        "horarios": descrever_horarios(config.horarios),
        "ranking": f"{NOMES_DOS_DIAS[config.ranking_dia]} às {formatar(config.ranking_horario)}",
        "votos_para_remover": config.votos_para_remover,
        "reacoes": config.reacoes.como_dict(),
        "fontes": [
            {
                "subreddit": fonte.subreddit,
                "categoria": fonte.categoria,
                "nivel": fonte.nivel,
                "chance": round(chances[fonte.subreddit], 4),
                "afinidade": termometro.afinidade.get(fonte.subreddit, 0.0),
            }
            for fonte in fontes
        ],
        "categorias": {
            nome: round(chance, 4)
            for nome, chance in sorted(
                termometro.chances_das_categorias(config.fontes, config.surpresa).items(), key=lambda item: -item[1]
            )
        },
        "em_alta": [nome for nome, _ in em_alta],
        "em_baixa": [nome for nome, _ in em_baixa],
        "recentes": historico.links_desde(quando - timedelta(days=DIAS_SEM_REPETIR)),
    }


def salvar_painel(caminho: Path | str, painel: dict) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(painel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporario, caminho)
