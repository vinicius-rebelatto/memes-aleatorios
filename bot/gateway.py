"""Conexão rápida com o gateway do Discord.

Durante muito tempo o Discord exigiu que um bot se conectasse ao gateway (o "modo
online") pelo menos uma vez antes de conseguir postar mensagens pela API. Este módulo
faz essa conexão: entra, se identifica, espera a confirmação ("READY") e sai.

O cliente da API (discord_api.py) só chama isto se o Discord recusar uma postagem com
o código 40001 e o token estiver válido. Na prática acontece no máximo uma vez.
"""

from __future__ import annotations

import json
import time

URL_GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"


class ErroGateway(Exception):
    pass


def _conectar_padrao(url: str, timeout: float):
    import websocket  # pacote websocket-client

    return websocket.create_connection(url, timeout=timeout)


def identificar_uma_vez(token: str, conectar=_conectar_padrao, limite_segundos: float = 20) -> None:
    conexao = conectar(URL_GATEWAY, timeout=limite_segundos)
    try:
        ola = json.loads(conexao.recv())
        if ola.get("op") != 10:
            raise ErroGateway(f"resposta inesperada do gateway: {ola}")
        conexao.send(
            json.dumps(
                {
                    "op": 2,
                    "d": {
                        "token": token,
                        "intents": 0,
                        "properties": {"os": "linux", "browser": "memes-aleatorios", "device": "memes-aleatorios"},
                    },
                }
            )
        )
        prazo = time.monotonic() + limite_segundos
        while time.monotonic() < prazo:
            evento = json.loads(conexao.recv())
            op = evento.get("op")
            if op == 0 and evento.get("t") == "READY":
                return
            if op == 1:  # o Discord pediu um "heartbeat"
                conexao.send(json.dumps({"op": 1, "d": None}))
            elif op == 9:
                raise ErroGateway("o Discord recusou a sessão (token inválido?)")
        raise ErroGateway("o Discord não confirmou a conexão a tempo")
    finally:
        try:
            conexao.close()
        except Exception:
            pass
