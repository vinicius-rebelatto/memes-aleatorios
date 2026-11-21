"""Histórico dos memes já postados (dados/historico.json).

O GitHub Actions salva este arquivo no repositório depois de cada post. É ele que
impede o bot de repetir meme e que liga cada mensagem do Discord ao meme original.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .fontes import Meme


class Historico:
    def __init__(self, caminho: Path, memes: list[dict] | None = None):
        self.caminho = Path(caminho)
        self.memes: list[dict] = []
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
        memes = dados.get("memes", []) if isinstance(dados, dict) else []
        return cls(caminho, [m for m in memes if isinstance(m, dict)])

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

    def registrar(self, meme: Meme, id_mensagem: str, quando: datetime) -> dict:
        registro = {
            "id_mensagem": str(id_mensagem),
            "fonte": meme.fonte,
            "chave": meme.chave,
            "subreddit": meme.subreddit,
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

    def por_mensagem(self, id_mensagem: str) -> dict | None:
        return self._por_mensagem.get(str(id_mensagem))

    def ids_de_mensagens(self) -> set[str]:
        return set(self._por_mensagem)

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = self.caminho.with_suffix(".tmp")
        conteudo = json.dumps({"memes": self.memes}, ensure_ascii=False, indent=2) + "\n"
        temporario.write_text(conteudo, encoding="utf-8")
        os.replace(temporario, self.caminho)
