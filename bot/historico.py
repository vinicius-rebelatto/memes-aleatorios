"""Histórico do que o bot já postou (dados/historico.json).

O GitHub Actions salva este arquivo no repositório. É ele que impede o bot de repetir
meme, de postar duas vezes no mesmo horário e de anunciar o Meme da Semana duas vezes,
e que liga cada mensagem do Discord ao meme original.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from .fontes import Meme


def _ler_data(texto: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(texto) if texto else None
    except ValueError:
        return None


class Historico:
    def __init__(self, caminho: Path, memes: list[dict] | None = None, rankings: list[dict] | None = None):
        self.caminho = Path(caminho)
        self.memes: list[dict] = []
        self.rankings: list[dict] = list(rankings or [])
        self._chaves: set[str] = set()
        self._imagens: set[str] = set()
        self._por_mensagem: dict[str, dict] = {}
        for registro in memes or []:
            self._indexar(registro)

    @classmethod
    def carregar(cls, caminho: Path | str) -> Historico:
        caminho = Path(caminho)
        if not caminho.exists():
            return cls(caminho)
        texto = caminho.read_text(encoding="utf-8").strip()
        dados = json.loads(texto) if texto else {}
        if not isinstance(dados, dict):
            dados = {}
        memes = [m for m in dados.get("memes", []) if isinstance(m, dict)]
        rankings = [r for r in dados.get("rankings", []) if isinstance(r, dict)]
        return cls(caminho, memes, rankings)

    def _indexar(self, registro: dict) -> None:
        self.memes.append(registro)
        if registro.get("chave"):
            self._chaves.add(registro["chave"])
        if registro.get("imagem") and registro.get("fonte") == "reddit":
            self._imagens.add(registro["imagem"])
        if registro.get("id_mensagem"):
            self._por_mensagem[str(registro["id_mensagem"])] = registro

    def ja_postado(self, meme: Meme) -> bool:
        if meme.chave in self._chaves:
            return True
        return bool(meme.imagem) and meme.imagem in self._imagens

    def postou_desde(self, momento: datetime) -> bool:
        """Já saiu algum meme a partir de `momento`?"""
        return any((quando := _ler_data(m.get("postado_em"))) and quando >= momento for m in self.memes)

    def links_desde(self, momento: datetime) -> list[str]:
        """Links dos posts do Reddit que o bot mandou a partir de `momento`."""
        return [
            m["link"]
            for m in self.memes
            if m.get("fonte") == "reddit" and m.get("link") and (quando := _ler_data(m.get("postado_em")))
            if quando >= momento
        ]

    def registrar(self, meme: Meme, id_mensagem: str, quando: datetime) -> dict:
        registro = {
            "id_mensagem": str(id_mensagem),
            "fonte": meme.fonte,
            "chave": meme.chave,
            "subreddit": meme.subreddit,
            "categoria": meme.categoria,
            "titulo": meme.titulo,
            "link": meme.link,
            "imagem": meme.imagem,
            "arquivo": meme.arquivo.name if meme.arquivo else "",
            "votos_reddit": meme.votos_reddit if meme.fonte == "reddit" else None,
            "nivel": meme.nivel,
            "nsfw": True if meme.nsfw else None,
            "postado_em": quando.isoformat(timespec="seconds"),
        }
        registro = {chave: valor for chave, valor in registro.items() if valor not in (None, "")}
        self._indexar(registro)
        return registro

    def registrar_ranking(self, id_mensagem: str, quando: datetime) -> None:
        self.rankings.append({"id_mensagem": str(id_mensagem), "postado_em": quando.isoformat(timespec="seconds")})

    def ultimo_ranking(self) -> date | None:
        """Dia (no horário de Brasília) em que saiu o último Meme da Semana."""
        datas = [quando.date() for r in self.rankings if (quando := _ler_data(r.get("postado_em")))]
        return max(datas) if datas else None

    def por_mensagem(self, id_mensagem: str) -> dict | None:
        return self._por_mensagem.get(str(id_mensagem))

    def ids_de_mensagens(self) -> set[str]:
        return set(self._por_mensagem)

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        dados = {"memes": self.memes, "rankings": self.rankings}
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporario, self.caminho)
