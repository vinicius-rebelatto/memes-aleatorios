import pytest
import requests
from conftest import RespostaFalsa, SessaoFalsa, snowflake

from bot.discord_api import API, Discord, ErroDiscord, link_da_mensagem, ms_do_snowflake


def cliente(respostas, identificar=None):
    sessao = SessaoFalsa(respostas)
    esperas = []
    chamadas_gateway = []
    discord = Discord(
        "tok",
        sessao=sessao,
        dormir=esperas.append,
        identificar=identificar or (lambda token: chamadas_gateway.append(token)),
    )
    return discord, sessao, esperas, chamadas_gateway


def test_envia_mensagem_com_token_e_corpo_json():
    discord, sessao, _, _ = cliente([RespostaFalsa(200, {"id": "42"})])
    assert discord.enviar("555", {"content": "oi"}) == {"id": "42"}
    metodo, url, opcoes = sessao.chamadas[0]
    assert (metodo, url) == ("POST", f"{API}/channels/555/messages")
    assert opcoes["headers"]["Authorization"] == "Bot tok"
    assert opcoes["json"] == {"content": "oi"}


def test_envia_arquivo_como_multipart():
    discord, sessao, _, _ = cliente([RespostaFalsa(200, {"id": "42"})])
    discord.enviar("555", {"embeds": []}, anexo=("meme.png", b"bytes", "image/png"))
    _, _, opcoes = sessao.chamadas[0]
    assert "json" not in opcoes
    assert opcoes["data"] == {"payload_json": '{"embeds": []}'}
    assert opcoes["files"] == {"files[0]": ("meme.png", b"bytes", "image/png")}


def test_espera_e_repete_quando_o_discord_pede_calma():
    discord, sessao, esperas, _ = cliente(
        [RespostaFalsa(429, {"retry_after": 1.5, "global": False}), RespostaFalsa(204)]
    )
    discord.reagir("555", "42", "😂")
    assert esperas == [1.75]
    assert len(sessao.chamadas) == 2


def test_repete_quando_o_discord_tem_erro_interno():
    discord, _, esperas, _ = cliente([RespostaFalsa(502, None), RespostaFalsa(200, {"id": "1"})])
    assert discord.eu() == {"id": "1"}
    assert esperas == [2]


def test_repete_quando_a_conexao_cai():
    discord, _, _, _ = cliente([requests.ConnectionError("caiu"), RespostaFalsa(200, {"id": "1"})])
    assert discord.eu() == {"id": "1"}


def test_erro_de_permissao_vem_com_dica():
    discord, _, _, _ = cliente([RespostaFalsa(403, {"code": 50013, "message": "Missing Permissions"})])
    with pytest.raises(ErroDiscord) as erro:
        discord.enviar("555", {"content": "oi"})
    assert erro.value.codigo == 50013
    assert "Falta permissão" in str(erro.value)


def test_reacao_vai_com_o_emoji_codificado_na_url():
    discord, sessao, _, _ = cliente([RespostaFalsa(204)])
    discord.reagir("555", "42", "😂")
    metodo, url, _ = sessao.chamadas[0]
    assert metodo == "PUT"
    assert url.endswith("/channels/555/messages/42/reactions/%F0%9F%98%82/@me")


def test_bot_novo_recusado_conecta_no_gateway_uma_vez_e_tenta_de_novo():
    discord, sessao, _, gateway = cliente(
        [
            RespostaFalsa(401, {"code": 40001, "message": "Unauthorized"}),
            RespostaFalsa(200, {"id": "999"}),  # GET /users/@me: o token é válido
            RespostaFalsa(200, {"id": "42"}),
        ]
    )
    assert discord.enviar("555", {"content": "oi"}) == {"id": "42"}
    assert gateway == ["tok"]
    assert [chamada[1] for chamada in sessao.chamadas][1] == f"{API}/users/@me"


def test_token_invalido_nao_tenta_o_gateway():
    discord, _, _, gateway = cliente(
        [
            RespostaFalsa(401, {"code": 40001, "message": "Unauthorized"}),
            RespostaFalsa(401, {"code": 0, "message": "401: Unauthorized"}),
        ]
    )
    with pytest.raises(ErroDiscord, match="DISCORD_TOKEN"):
        discord.enviar("555", {"content": "oi"})
    assert gateway == []


def test_falha_no_gateway_vira_erro_claro():
    def gateway_quebrado(token):
        raise OSError("sem rede")

    discord, _, _, _ = cliente(
        [RespostaFalsa(401, {"code": 40001, "message": "Unauthorized"}), RespostaFalsa(200, {"id": "9"})],
        identificar=gateway_quebrado,
    )
    with pytest.raises(ErroDiscord, match="gateway"):
        discord.enviar("555", {"content": "oi"})


def test_mensagens_desde_pagina_ate_chegar_na_data():
    agora_ms = 1_795_000_000_000
    minuto = 60_000
    pagina1 = [{"id": snowflake(agora_ms - i * minuto)} for i in range(100)]
    pagina2 = [{"id": snowflake(agora_ms - (100 + i) * minuto)} for i in range(100)]
    desde = agora_ms - 149 * minuto
    discord, sessao, _, _ = cliente([RespostaFalsa(200, pagina1), RespostaFalsa(200, pagina2)])

    mensagens = discord.mensagens_desde("555", desde)

    assert len(mensagens) == 150
    assert all(ms_do_snowflake(m["id"]) >= desde for m in mensagens)
    assert sessao.chamadas[1][2]["params"]["before"] == pagina1[-1]["id"]


def test_snowflake_e_link_da_mensagem():
    assert ms_do_snowflake(snowflake(1_795_000_123_456)) == 1_795_000_123_456
    assert link_da_mensagem("1", "2", "3") == "https://discord.com/channels/1/2/3"
