import json
from datetime import datetime, timezone

import pytest
from conftest import DiscordFalso

import bot.postar as modulo_postar
from bot.discord_api import ErroDiscord
from bot.fontes import Meme
from bot.historico import Historico
from bot.postar import SemMemeNovo, main, montar_mensagem, postar


def meme_do_reddit(titulo="eu_nvr"):
    return Meme(
        fonte="reddit",
        chave="https://redd.it/abc",
        titulo=titulo,
        imagem="https://i.redd.it/abc.png",
        link="https://redd.it/abc",
        subreddit="eu_nvr",
        votos_reddit=744,
    )


def test_mensagem_do_reddit_tem_imagem_fonte_e_rodape(config):
    corpo, anexo = montar_mensagem(meme_do_reddit(), config)
    embed = corpo["embeds"][0]
    assert anexo is None
    assert embed["image"] == {"url": "https://i.redd.it/abc.png"}
    assert embed["author"] == {"name": "r/eu_nvr", "url": "https://redd.it/abc"}
    assert "title" not in embed  # o título só repetia o nome do subreddit
    assert embed["footer"]["text"] == "⬆️ 744 no Reddit • 😂 vota no Meme da Semana • 🚫 passou do ponto"
    assert corpo["allowed_mentions"] == {"parse": []}


def test_titulo_informativo_aparece(config):
    corpo, _ = montar_mensagem(meme_do_reddit("quando o deploy é sexta"), config)
    assert corpo["embeds"][0]["title"] == "quando o deploy é sexta"
    assert corpo["embeds"][0]["url"] == "https://redd.it/abc"


def test_mensagem_do_estoque_envia_o_arquivo(config):
    arquivo = config.estoque_pasta / "Zoeira Boa.JPG"
    arquivo.write_bytes(b"jpg")
    corpo, anexo = montar_mensagem(Meme(fonte="estoque", chave="estoque/Zoeira Boa.JPG", arquivo=arquivo), config)
    assert anexo == ("meme.jpg", b"jpg", "image/jpeg")
    assert corpo["embeds"][0]["image"] == {"url": "attachment://meme.jpg"}
    assert corpo["attachments"] == [{"id": 0, "filename": "meme.jpg"}]


def test_fluxo_completo_posta_reage_e_registra(config, tmp_path):
    discord = DiscordFalso()
    historico = Historico(tmp_path / "h.json")
    registro = postar(discord, config, historico, "555", escolher=meme_do_reddit, log=lambda *_: None)

    assert len(discord.enviadas) == 1
    assert discord.enviadas[0]["canal"] == "555"
    assert discord.reacoes == [("5001", "😂"), ("5001", "🚫")]
    assert discord.dormidas == [0.3]
    assert registro["id_mensagem"] == "5001"
    assert historico.ja_postado(meme_do_reddit())


def test_sem_meme_novo_da_erro_e_nao_posta(config, tmp_path):
    discord = DiscordFalso()
    with pytest.raises(SemMemeNovo):
        postar(discord, config, Historico(tmp_path / "h.json"), "555", escolher=lambda: None, log=lambda *_: None)
    assert discord.enviadas == []


def test_problema_na_moderacao_ou_na_reacao_nao_impede_o_post(config, tmp_path):
    class DiscordMeioQuebrado(DiscordFalso):
        def mensagens(self, *args, **kwargs):
            raise ErroDiscord(403, 50001, "Missing Access", "GET")

        def reagir(self, canal_id, mensagem_id, emoji):
            raise ErroDiscord(403, 50013, "Missing Permissions", "PUT")

    historico = Historico(tmp_path / "h.json")
    historico.registrar(meme_do_reddit("antigo"), "4000", datetime(2026, 1, 1, tzinfo=timezone.utc))  # algo para moderar
    novo = Meme(fonte="reddit", chave="x", imagem="https://i.redd.it/x.png", link="x", subreddit="me_irl")
    avisos = []
    discord = DiscordMeioQuebrado()
    postar(discord, config, historico, "555", escolher=lambda: novo, log=avisos.append)
    assert len(discord.enviadas) == 1
    assert any("moderar" in aviso for aviso in avisos)
    assert sum("reagir" in aviso for aviso in avisos) == 2


def test_sem_secrets_o_bot_avisa_e_sai_sem_erro(monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main([]) == 0
    assert "ainda não foram configurados" in capsys.readouterr().out


def test_secret_errado_falha(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "nome-do-canal")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main([]) == 1


def test_simular_mostra_o_post_sem_usar_o_discord(monkeypatch, capsys):
    monkeypatch.setattr(modulo_postar, "escolher_meme", lambda config, ja_postado: meme_do_reddit())
    assert main(["--simular"]) == 0
    saida = capsys.readouterr().out
    corpo = json.loads(saida.split("\n", 1)[1])
    assert corpo["embeds"][0]["image"]["url"] == "https://i.redd.it/abc.png"
