import json

import pytest

from bot.gateway import ErroGateway, identificar_uma_vez


class ConexaoFalsa:
    def __init__(self, eventos):
        self.eventos = [json.dumps(evento) for evento in eventos]
        self.enviados = []
        self.fechada = False

    def recv(self):
        return self.eventos.pop(0)

    def send(self, texto):
        self.enviados.append(json.loads(texto))

    def close(self):
        self.fechada = True


def conectar_com(conexao):
    return lambda url, timeout: conexao


def test_conecta_identifica_e_sai_quando_fica_pronto():
    conexao = ConexaoFalsa(
        [
            {"op": 10, "d": {"heartbeat_interval": 41250}},
            {"op": 1, "d": None},
            {"op": 0, "t": "READY", "s": 1, "d": {}},
        ]
    )
    identificar_uma_vez("tok", conectar=conectar_com(conexao))
    identificacao, batimento = conexao.enviados
    assert identificacao["op"] == 2
    assert identificacao["d"]["token"] == "tok"
    assert identificacao["d"]["intents"] == 0
    assert batimento["op"] == 1
    assert conexao.fechada


def test_sessao_recusada_vira_erro():
    conexao = ConexaoFalsa([{"op": 10, "d": {}}, {"op": 9, "d": False}])
    with pytest.raises(ErroGateway):
        identificar_uma_vez("tok", conectar=conectar_com(conexao))
    assert conexao.fechada


def test_resposta_estranha_vira_erro():
    conexao = ConexaoFalsa([{"op": 0, "t": "OUTRA_COISA"}])
    with pytest.raises(ErroGateway):
        identificar_uma_vez("tok", conectar=conectar_com(conexao))
