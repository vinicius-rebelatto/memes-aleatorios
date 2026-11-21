"""Cliente mínimo da API REST do Discord: só o que o bot usa.

O bot não fica online o tempo todo. Cada execução do GitHub Actions faz algumas
chamadas HTTP (postar, reagir, ler reações, apagar) e termina.
"""

from __future__ import annotations

import json
import time
import urllib.parse

import requests

from . import gateway

API = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/vinicius-rebelatto/memes-aleatorios, 1.0)"
EPOCA_DISCORD_MS = 1_420_070_400_000

DICAS = {
    40001: "O token foi recusado. Confira o secret DISCORD_TOKEN (gere outro em Bot → Reset Token).",
    50001: "O bot não consegue ver o canal. Confira se ele foi convidado para o servidor e se tem acesso ao canal.",
    50013: (
        "Falta permissão para o bot nesse canal: ver canal, enviar mensagens, inserir links, "
        "anexar arquivos, adicionar reações e ver histórico."
    ),
    10003: "Canal não encontrado. Confira o secret DISCORD_CHANNEL_ID.",
    10008: "Mensagem não encontrada (talvez alguém já tenha apagado).",
    10014: "Emoji desconhecido. Use um emoji padrão no config.yml.",
}
DICAS_POR_STATUS = {401: DICAS[40001], 403: DICAS[50013], 404: "Recurso não encontrado."}


class ErroDiscord(Exception):
    def __init__(self, status: int, codigo: int | None, mensagem: str, rota: str):
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.rota = rota
        texto = f"Discord respondeu {status} em {rota}: {mensagem}"
        if codigo:
            texto += f" (código {codigo})"
        dica = DICAS.get(codigo or 0) or DICAS_POR_STATUS.get(status, "")
        if dica:
            texto += f". {dica}"
        super().__init__(texto)


def ms_do_snowflake(snowflake: str | int) -> int:
    """Converte o ID de uma mensagem do Discord no horário (em milissegundos) em que ela foi criada."""
    return (int(snowflake) >> 22) + EPOCA_DISCORD_MS


def link_da_mensagem(servidor_id: str, canal_id: str, mensagem_id: str) -> str:
    return f"https://discord.com/channels/{servidor_id}/{canal_id}/{mensagem_id}"


def _detalhes_do_erro(resposta) -> tuple[int | None, str]:
    try:
        corpo = resposta.json()
    except ValueError:
        return None, (resposta.text or "")[:200]
    if isinstance(corpo, dict):
        return corpo.get("code"), str(corpo.get("message") or corpo)[:300]
    return None, str(corpo)[:200]


def _segundos_para_esperar(resposta) -> float:
    try:
        corpo = resposta.json()
        if isinstance(corpo, dict) and "retry_after" in corpo:
            return float(corpo["retry_after"])
    except ValueError:
        pass
    try:
        return float(resposta.headers.get("Retry-After", 1))
    except (TypeError, ValueError):
        return 1.0


class Discord:
    def __init__(self, token: str, sessao=None, dormir=time.sleep, identificar=None):
        self.token = token
        self.sessao = sessao or requests.Session()
        self.dormir = dormir
        self.identificar = identificar or gateway.identificar_uma_vez
        self._ja_identificou = False
        self._eu: dict | None = None
        self._canais: dict[str, dict] = {}

    @property
    def _cabecalhos(self) -> dict:
        return {"Authorization": f"Bot {self.token}", "User-Agent": USER_AGENT}

    def _requisicao(self, metodo: str, rota: str, *, corpo=None, params=None, anexo=None, tentativas: int = 5):
        url = API + rota
        descricao = f"{metodo} {rota}"
        for tentativa in range(1, tentativas + 1):
            opcoes = {"headers": self._cabecalhos, "params": params, "timeout": 30}
            if anexo is not None:
                nome, conteudo, tipo = anexo
                opcoes["data"] = {"payload_json": json.dumps(corpo or {})}
                opcoes["files"] = {"files[0]": (nome, conteudo, tipo)}
            elif corpo is not None:
                opcoes["json"] = corpo
            try:
                resposta = self.sessao.request(metodo, url, **opcoes)
            except requests.RequestException as erro:
                if tentativa == tentativas:
                    raise ErroDiscord(0, None, f"falha de conexão ({erro})", descricao) from erro
                self.dormir(2 * tentativa)
                continue

            status = resposta.status_code
            if status == 429:
                self.dormir(_segundos_para_esperar(resposta) + 0.25)
                continue
            if status >= 500 and tentativa < tentativas:
                self.dormir(2 * tentativa)
                continue
            if status >= 400:
                codigo, mensagem = _detalhes_do_erro(resposta)
                if codigo == 40001 and self._conectar_se_preciso(rota):
                    continue
                raise ErroDiscord(status, codigo, mensagem, descricao)
            if status == 204 or not resposta.content:
                return None
            return resposta.json()
        raise ErroDiscord(429, None, "o Discord pediu para esperar várias vezes seguidas", descricao)

    def _conectar_se_preciso(self, rota: str) -> bool:
        """Se o token é válido mas o Discord recusou, conecta no gateway uma vez e tenta de novo."""
        if self._ja_identificou or rota == "/users/@me":
            return False
        self._ja_identificou = True
        resposta = self.sessao.request("GET", API + "/users/@me", headers=self._cabecalhos, timeout=30)
        if resposta.status_code != 200:
            return False  # o token é inválido mesmo
        print("ℹ️ Conectando o bot ao Discord uma vez (exigência para bots novos)...")
        try:
            self.identificar(self.token)
        except Exception as erro:
            raise ErroDiscord(401, None, f"não consegui conectar o bot ao gateway ({erro})", "gateway") from erro
        return True

    # ---- chamadas usadas pelo bot -------------------------------------------------

    def eu(self) -> dict:
        """Dados do próprio bot (id, nome)."""
        if self._eu is None:
            self._eu = self._requisicao("GET", "/users/@me")
        return self._eu

    def canal(self, canal_id: str) -> dict:
        """Dados do canal (inclui o guild_id, o ID do servidor)."""
        if canal_id not in self._canais:
            self._canais[canal_id] = self._requisicao("GET", f"/channels/{canal_id}")
        return self._canais[canal_id]

    def enviar(self, canal_id: str, corpo: dict, anexo: tuple | None = None) -> dict:
        """Posta uma mensagem. `anexo` é (nome, bytes, tipo) para enviar um arquivo junto."""
        return self._requisicao("POST", f"/channels/{canal_id}/messages", corpo=corpo, anexo=anexo)

    def reagir(self, canal_id: str, mensagem_id: str, emoji: str) -> None:
        emoji_url = urllib.parse.quote(emoji, safe="")
        self._requisicao("PUT", f"/channels/{canal_id}/messages/{mensagem_id}/reactions/{emoji_url}/@me")

    def apagar(self, canal_id: str, mensagem_id: str) -> None:
        self._requisicao("DELETE", f"/channels/{canal_id}/messages/{mensagem_id}")

    def mensagens(self, canal_id: str, limite: int = 100, antes: str | None = None) -> list[dict]:
        """Mensagens mais recentes do canal (das mais novas para as mais antigas)."""
        params = {"limit": max(1, min(int(limite), 100))}
        if antes:
            params["before"] = antes
        return self._requisicao("GET", f"/channels/{canal_id}/messages", params=params) or []

    def mensagens_desde(self, canal_id: str, desde_ms: int, maximo: int = 2000) -> list[dict]:
        """Todas as mensagens do canal criadas a partir de `desde_ms` (milissegundos)."""
        resultado: list[dict] = []
        antes = None
        while len(resultado) < maximo:
            lote = self.mensagens(canal_id, 100, antes)
            if not lote:
                break
            recentes = [m for m in lote if ms_do_snowflake(m["id"]) >= desde_ms]
            resultado.extend(recentes)
            if len(recentes) < len(lote) or len(lote) < 100:
                break
            antes = str(min(int(m["id"]) for m in lote))
        return resultado
