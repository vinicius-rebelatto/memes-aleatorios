from datetime import datetime, timezone

from conftest import DiscordFalso, reacao

from bot.discord_api import ErroDiscord
from bot.fontes import Meme
from bot.historico import Historico
from bot.moderar import moderar
from bot.util import contar_reacao, mesmo_emoji

QUANDO = datetime(2026, 11, 21, tzinfo=timezone.utc)


def historico_com_memes(tmp_path, *ids):
    historico = Historico(tmp_path / "h.json")
    for numero, id_mensagem in enumerate(ids):
        meme = Meme(fonte="reddit", chave=f"https://redd.it/p{numero}", link=f"https://redd.it/p{numero}")
        historico.registrar(meme, id_mensagem, QUANDO)
    return historico


def test_contar_reacao_desconta_o_proprio_bot():
    mensagem = {"reactions": [reacao("😂", 4, do_bot=True), reacao("🚫", 2)]}
    assert contar_reacao(mensagem, "😂") == 3
    assert contar_reacao(mensagem, "🚫") == 2
    assert contar_reacao(mensagem, "🔥") == 0
    assert contar_reacao({}, "😂") == 0


def test_emoji_com_e_sem_seletor_de_variacao_sao_iguais():
    assert mesmo_emoji("❤️", "❤")
    assert not mesmo_emoji("😂", "🚫")
    assert not mesmo_emoji(None, "😂")


def test_apaga_so_o_meme_do_bot_com_votos_suficientes(config, tmp_path):
    historico = historico_com_memes(tmp_path, "1001", "1002")
    discord = DiscordFalso(
        [
            {"id": "1001", "reactions": [reacao("🚫", 4, do_bot=True)]},  # 3 pessoas: apaga
            {"id": "1002", "reactions": [reacao("🚫", 3, do_bot=True)]},  # 2 pessoas: fica
            {"id": "3000", "reactions": [reacao("🚫", 10)]},  # post da galera: não mexe
        ]
    )
    removidos = moderar(discord, config, historico, "555", log=lambda *_: None)
    assert discord.apagadas == ["1001"]
    assert removidos[0]["link"] == "https://redd.it/p0"


def test_sem_memes_no_historico_nem_consulta_o_discord(config, tmp_path):
    class DiscordQueNaoPodeSerUsado(DiscordFalso):
        def mensagens(self, *args, **kwargs):
            raise AssertionError("não devia consultar o canal")

    assert moderar(DiscordQueNaoPodeSerUsado(), config, Historico(tmp_path / "h.json"), "555") == []


def test_meme_ja_apagado_por_alguem_nao_quebra(config, tmp_path):
    historico = historico_com_memes(tmp_path, "1001")

    class DiscordComMensagemSumida(DiscordFalso):
        def apagar(self, canal_id, mensagem_id):
            raise ErroDiscord(404, 10008, "Unknown Message", "DELETE")

    discord = DiscordComMensagemSumida([{"id": "1001", "reactions": [reacao("🚫", 5, do_bot=True)]}])
    assert moderar(discord, config, historico, "555", log=lambda *_: None) == []
