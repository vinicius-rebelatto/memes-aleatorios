"""O termômetro da galera: a régua de peso e a afinidade de cada fonte.

- Cada meme do bot chega com 5 reações: 😂 engraçado, 👍 curti, 😐 sem graça, 🌶️ mais pesado e
  🚫 passou do ponto.
- 🌶️ sobe a régua e 🚫 desce. A régua vai de 1 (leve) a 5 (pesado).
- 😂 e 😐 dão nota para a fonte do meme (a "afinidade"): fonte que leva 😂 aparece mais.
- Na hora de escolher o próximo meme, o bot prefere fontes com nível perto da régua e
  com afinidade alta.

O estado fica em dados/termometro.json, que o GitHub Actions salva junto com o histórico.
Cada voto é contado uma vez só: o bot guarda quantas reações já tinha visto em cada meme
e, a cada leitura, aplica só a diferença.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

from .config import Fonte, Reacoes
from .discord_api import ms_do_snowflake
from .util import contar_reacao

PASSO_DA_REGUA = 0.15  # quanto cada voto 🌶️ ou 🚫 move a régua
PASSO_DA_AFINIDADE = 0.35  # quanto cada 😂/👍 ou 😐 move a nota do subreddit
PASSO_DA_CATEGORIA = 0.15  # e a nota da categoria dele
AFINIDADE_MAXIMA = 3.0
ESPALHAMENTO = 1.2  # o quanto uma categoria pode estar longe da régua e ainda aparecer
DIAS_CONTANDO_VOTOS = 7  # votos em memes com mais de 7 dias não mexem mais no termômetro
REGUA_MINIMA, REGUA_MAXIMA = 1.0, 5.0
TAMANHO_DA_EVOLUCAO = 500
CORES_DA_REGUA = ("🟩", "🟩", "🟨", "🟧", "🟥")  # leve → pesado


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def proximidade(nivel: float, regua: float) -> float:
    """1.0 quando o nível é igual à régua; cai conforme se afasta (0.71 a 1 nível, 0.25 a 2, 0.04 a 3)."""
    return math.exp(-((nivel - regua) ** 2) / (2 * ESPALHAMENTO**2))


def multiplicador(afinidade: float) -> float:
    """Nota +3 deixa a fonte ~20x mais provável; -3, ~20x menos (some quase de vez)."""
    return math.exp(afinidade)


def numero_br(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def barra(regua: float) -> str:
    """Desenho da régua com 5 quadradinhos, ex.: 3,4 → 🟩🟩🟨⬜⬜."""
    cheios = int(_limitar(round(regua), 1, 5))
    return "".join(CORES_DA_REGUA[i] if i < cheios else "⬜" for i in range(5))


class Termometro:
    def __init__(
        self,
        caminho: Path | str,
        regua: float = 3.0,
        afinidade: dict | None = None,
        votos_contados: dict | None = None,
        evolucao: list | None = None,
        afinidade_categorias: dict | None = None,
    ):
        self.caminho = Path(caminho)
        self.regua = _limitar(float(regua), REGUA_MINIMA, REGUA_MAXIMA)
        self.afinidade: dict[str, float] = {str(k): float(v) for k, v in (afinidade or {}).items()}
        self.votos_contados: dict[str, dict[str, int]] = dict(votos_contados or {})
        self.evolucao: list[dict] = list(evolucao or [])
        self.afinidade_categorias: dict[str, float] = {
            str(k): float(v) for k, v in (afinidade_categorias or {}).items()
        }

    @classmethod
    def carregar(cls, caminho: Path | str, regua_inicial: float = 3.0) -> "Termometro":
        caminho = Path(caminho)
        dados = {}
        if caminho.exists():
            texto = caminho.read_text(encoding="utf-8").strip()
            dados = json.loads(texto) if texto else {}
        if not isinstance(dados, dict):
            dados = {}
        return cls(
            caminho,
            regua=dados.get("regua", regua_inicial),
            afinidade=dados.get("afinidade"),
            votos_contados=dados.get("votos_contados"),
            evolucao=dados.get("evolucao"),
            afinidade_categorias=dados.get("afinidade_categorias"),
        )

    def salvar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {
            "regua": round(self.regua, 3),
            "afinidade": dict(sorted(self.afinidade.items())),
            "afinidade_categorias": dict(sorted(self.afinidade_categorias.items())),
            "evolucao": self.evolucao,
            "votos_contados": self.votos_contados,
        }
        temporario = self.caminho.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporario, self.caminho)

    # ---- votos -------------------------------------------------------------------

    def contar_votos(self, mensagem: dict, registro: dict, reacoes: Reacoes) -> dict[str, int]:
        """Aplica os votos novos de um meme (desde a última leitura). Devolve a diferença por reação."""
        atuais = {nome: contar_reacao(mensagem, emoji) for nome, emoji in reacoes.como_dict().items()}
        anteriores = self.votos_contados.get(str(mensagem["id"]), {})
        diferenca = {nome: atuais[nome] - int(anteriores.get(nome, 0)) for nome in atuais}

        movimento = PASSO_DA_REGUA * (diferenca["mais_pesado"] - diferenca["passou_do_ponto"])
        self.regua = round(_limitar(self.regua + movimento, REGUA_MINIMA, REGUA_MAXIMA), 3)

        if registro.get("fonte") == "reddit" and registro.get("subreddit"):
            saldo = diferenca["engracado"] + diferenca.get("curti", 0) - diferenca["sem_graca"]
            subreddit = registro["subreddit"]
            nota = self.afinidade.get(subreddit, 0.0) + PASSO_DA_AFINIDADE * saldo
            self.afinidade[subreddit] = round(_limitar(nota, -AFINIDADE_MAXIMA, AFINIDADE_MAXIMA), 3)
            if registro.get("categoria"):
                categoria = registro["categoria"]
                nota = self.afinidade_categorias.get(categoria, 0.0) + PASSO_DA_CATEGORIA * saldo
                self.afinidade_categorias[categoria] = round(_limitar(nota, -AFINIDADE_MAXIMA, AFINIDADE_MAXIMA), 3)

        self.votos_contados[str(mensagem["id"])] = atuais
        return diferenca

    def atualizar(self, mensagens: list[dict], historico, reacoes: Reacoes, quando: datetime) -> bool:
        """Conta os votos novos de todos os memes recentes do bot. Devolve True se algo mudou."""
        limite_ms = (quando - timedelta(days=DIAS_CONTANDO_VOTOS)).timestamp() * 1000
        antes = json.dumps([self.regua, self.afinidade, self.afinidade_categorias, self.votos_contados], sort_keys=True)

        for mensagem in mensagens:
            registro = historico.por_mensagem(mensagem.get("id", ""))
            if registro is None or ms_do_snowflake(mensagem["id"]) < limite_ms:
                continue  # só memes do próprio bot, dos últimos dias
            self.contar_votos(mensagem, registro, reacoes)

        # memes antigos saem da conta (os votos deles já foram aplicados)
        self.votos_contados = {
            mensagem_id: votos
            for mensagem_id, votos in self.votos_contados.items()
            if ms_do_snowflake(mensagem_id) >= limite_ms
        }
        mudou = (
            json.dumps([self.regua, self.afinidade, self.afinidade_categorias, self.votos_contados], sort_keys=True)
            != antes
        )
        if not self.evolucao or self.evolucao[-1].get("regua") != self.regua:
            self.evolucao.append({"quando": quando.isoformat(timespec="seconds"), "regua": self.regua})
            self.evolucao = self.evolucao[-TAMANHO_DA_EVOLUCAO:]
            mudou = True
        return mudou

    # ---- leitura -----------------------------------------------------------------

    def pesos(self, fontes: tuple[Fonte, ...], surpresa: bool = False) -> dict[str, float]:
        """Chance de cada subreddit ser a primeira tentativa (somando 1), em dois passos:

        1. sorteia a categoria: peso × perto da régua (num post surpresa, sem régua) × nota da categoria;
        2. dentro dela, o subreddit: peso × nota do subreddit. Quem leva 😂/👍 se sobressai e quem
           leva 😐 vai sumindo.
        Fonte sem nível (ex.: jogos) fica fora da régua.
        """
        grupos: dict[str, list[Fonte]] = {}
        for fonte in fontes:
            grupos.setdefault(fonte.grupo, []).append(fonte)

        def peso_do_grupo(nome: str, membros: list[Fonte]) -> float:
            primeira = membros[0]
            perto = 1.0
            if not surpresa and primeira.segue_a_regua:
                perto = proximidade(primeira.nivel, self.regua)
            if primeira.categoria:
                return primeira.peso_categoria * perto * multiplicador(self.afinidade_categorias.get(nome, 0.0))
            return primeira.peso * perto * multiplicador(self.afinidade.get(primeira.subreddit, 0.0))

        pesos_dos_grupos = {nome: peso_do_grupo(nome, membros) for nome, membros in grupos.items()}
        total = sum(pesos_dos_grupos.values()) or 1.0
        resultado: dict[str, float] = {}
        for nome, membros in grupos.items():
            dentro = {f.subreddit: f.peso * multiplicador(self.afinidade.get(f.subreddit, 0.0)) for f in membros}
            soma = sum(dentro.values()) or 1.0
            for subreddit, peso in dentro.items():
                resultado[subreddit] = pesos_dos_grupos[nome] / total * peso / soma
        return resultado

    def chances(self, fontes: tuple[Fonte, ...], surpresa: float) -> dict[str, float]:
        """Probabilidade de cada fonte ser a primeira tentativa do próximo meme, contando os posts surpresa."""
        normal = self.pesos(fontes)
        sorteio = self.pesos(fontes, surpresa=True)
        return {nome: (1 - surpresa) * normal[nome] + surpresa * sorteio[nome] for nome in normal}

    def chances_das_categorias(self, fontes: tuple[Fonte, ...], surpresa: float) -> dict[str, float]:
        chances = self.chances(fontes, surpresa)
        resultado: dict[str, float] = {}
        for fonte in fontes:
            resultado[fonte.grupo] = resultado.get(fonte.grupo, 0.0) + chances[fonte.subreddit]
        return resultado

    def variacao_desde(self, momento: datetime) -> float:
        """Quanto a régua andou desde `momento` (positivo = ficou mais pesada)."""
        referencia = None
        for ponto in self.evolucao:
            try:
                quando = datetime.fromisoformat(ponto["quando"])
            except (KeyError, TypeError, ValueError):
                continue
            if quando <= momento:
                referencia = ponto["regua"]
            elif referencia is None:
                referencia = ponto["regua"]  # o termômetro começou depois de `momento`
                break
            else:
                break
        return 0.0 if referencia is None else round(self.regua - float(referencia), 3)

    def descrever_regua(self) -> str:
        return f"{numero_br(self.regua)}/5 {barra(self.regua)}"

    def fontes_em_destaque(
        self, quantidade: int = 2, fontes: tuple[Fonte, ...] | None = None
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
        """(em alta, em baixa): fontes com maior e menor afinidade, ignorando as neutras.

        Com `fontes`, só entram as que ainda estão no config.yml.
        """
        ativas = None if fontes is None else {fonte.subreddit for fonte in fontes}
        notas = [(s, a) for s, a in self.afinidade.items() if ativas is None or s in ativas]
        positivas = sorted(((s, a) for s, a in notas if a > 0), key=lambda x: -x[1])
        negativas = sorted(((s, a) for s, a in notas if a < 0), key=lambda x: x[1])
        return positivas[:quantidade], negativas[:quantidade]
