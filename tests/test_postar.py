import json
from datetime import timedelta

import pytest
from conftest import DiscordFalso, reacoes_do_bot, snowflake

import bot.postar as modulo_postar
from bot.discord_api import ErroDiscord
from bot.fontes import Meme
from bot.historico import Historico
from bot.postar import SemMemeNovo, main, montar_mensagem, postar
from bot.termometro import Termometro
from bot.util import agora

LEGENDA = "😂 engraçado · 😐 sem graça · 🌶️ mais pesado · 🚫 passou do ponto"


def meme_do_reddit(titulo="eu_nvr", nsfw=False):
    return Meme(
        fonte="reddit",
        chave="https://redd.it/abc",
        titulo=titulo,
        imagem="https://i.redd.it/abc.png",
        link="https://redd.it/abc",
        subreddit="eu_nvr",
        votos_reddit=744,
        nsfw=nsfw,
        nivel=4,
    )


def test_mensagem_do_reddit_tem_imagem_fonte_regua_e_legenda(config):
    corpo, anexo = montar_mensagem(meme_do_reddit(), config, regua=3.35)
    embed = corpo["embeds"][0]
    assert anexo is None
    assert embed["image"] == {"url": "https://i.redd.it/abc.png"}
    assert embed["author"] == {"name": "r/eu_nvr", "url": "https://redd.it/abc"}
    assert "title" not in embed  # o título só repetia o nome do subreddit
    assert embed["footer"]["text"] == f"⬆️ 744 no Reddit • 🌡️ régua 3,4/5 • {LEGENDA}"
    assert corpo["allowed_mentions"] == {"parse": []}


def test_titulo_informativo_aparece_e_nsfw_ganha_aviso(config):
    corpo, _ = montar_mensagem(meme_do_reddit("quando o deploy é sexta", nsfw=True), config)
    embed = corpo["embeds"][0]
    assert embed["title"] == "quando o deploy é sexta"
    assert embed["url"] == "https://redd.it/abc"
    assert embed["author"]["name"] == "🔞 r/eu_nvr"


def test_mensagem_do_estoque_envia_o_arquivo(config):
    arquivo = config.estoque_pasta / "Zoeira Boa.JPG"
    arquivo.write_bytes(b"jpg")
    meme = Meme(fonte="estoque", chave="estoque/Zoeira Boa.JPG", arquivo=arquivo)
    corpo, anexo = montar_mensagem(meme, config)
    assert anexo == ("meme.jpg", b"jpg", "image/jpeg")
    assert corpo["embeds"][0]["image"] == {"url": "attachment://meme.jpg"}
    assert corpo["embeds"][0]["footer"]["text"] == LEGENDA
    assert corpo["attachments"] == [{"id": 0, "filename": "meme.jpg"}]


def test_fluxo_completo_posta_com_as_4_reacoes_e_registra(config, tmp_path):
    discord = DiscordFalso()
    historico = Historico(tmp_path / "h.json")
    termometro = Termometro(tmp_path / "t.json")
    registro = postar(discord, config, historico, termometro, "555", escolher=meme_do_reddit, log=lambda *_: None)

    assert len(discord.enviadas) == 1
    assert discord.enviadas[0]["canal"] == "555"
    assert discord.reacoes == [("5001", "😂"), ("5001", "😐"), ("5001", "🌶️"), ("5001", "🚫")]
    assert discord.dormidas == [0.35, 0.35, 0.35]
    assert registro["id_mensagem"] == "5001"
    assert registro["nivel"] == 4
    assert historico.ja_postado(meme_do_reddit())


def test_votos_da_galera_mexem_na_regua_antes_do_proximo_post(config, tmp_path):
    historico = Historico(tmp_path / "h.json")
    anterior = snowflake(int((agora() - timedelta(hours=3)).timestamp() * 1000))
    historico.registrar(Meme(fonte="reddit", chave="x", subreddit="eu_nvr", link="x"), anterior, agora())
    discord = DiscordFalso([{"id": anterior, "reactions": reacoes_do_bot(engracado=1, mais_pesado=2)}])
    termometro = Termometro(tmp_path / "t.json")

    postar(discord, config, historico, termometro, "555", escolher=meme_do_reddit, log=lambda *_: None)

    assert termometro.regua == pytest.approx(3.3)
    assert termometro.afinidade == {"eu_nvr": pytest.approx(0.25)}
    rodape = discord.enviadas[0]["corpo"]["embeds"][0]["footer"]["text"]
    assert "🌡️ régua 3,3/5" in rodape


def test_nsfw_so_vale_em_canal_restrito_por_idade(config, tmp_path):
    avisos = []
    postar(
        DiscordFalso(canal_nsfw=False),
        config,
        Historico(tmp_path / "h.json"),
        Termometro(tmp_path / "t.json"),
        "555",
        escolher=meme_do_reddit,
        log=avisos.append,
    )
    assert any("restrito por idade" in aviso for aviso in avisos)

    avisos = []
    postar(
        DiscordFalso(canal_nsfw=True),
        config,
        Historico(tmp_path / "h2.json"),
        Termometro(tmp_path / "t2.json"),
        "555",
        escolher=meme_do_reddit,
        log=avisos.append,
    )
    assert not any("restrito por idade" in aviso for aviso in avisos)


def test_sem_meme_novo_da_erro_e_nao_posta(config, tmp_path):
    discord = DiscordFalso()
    with pytest.raises(SemMemeNovo):
        postar(
            discord,
            config,
            Historico(tmp_path / "h.json"),
            Termometro(tmp_path / "t.json"),
            "555",
            escolher=lambda: None,
            log=lambda *_: None,
        )
    assert discord.enviadas == []


def test_problema_ao_ler_ou_reagir_nao_impede_o_post(config, tmp_path):
    class DiscordMeioQuebrado(DiscordFalso):
        def mensagens_desde(self, *args, **kwargs):
            raise ErroDiscord(403, 50001, "Missing Access", "GET")

        def reagir(self, canal_id, mensagem_id, emoji):
            raise ErroDiscord(403, 50013, "Missing Permissions", "PUT")

    avisos = []
    discord = DiscordMeioQuebrado()
    termometro = Termometro(tmp_path / "t.json")
    postar(
        discord, config, Historico(tmp_path / "h.json"), termometro, "555", escolher=meme_do_reddit, log=avisos.append
    )
    assert len(discord.enviadas) == 1
    assert any("ler as reações" in aviso for aviso in avisos)
    assert sum("reagir" in aviso for aviso in avisos) == 4


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


def test_simular_testa_as_fontes_e_mostra_o_post_sem_usar_o_discord(monkeypatch, capsys):
    monkeypatch.setattr(modulo_postar, "buscar_memes", lambda subreddit: [meme_do_reddit()])
    monkeypatch.setattr(modulo_postar, "escolher_meme", lambda *args, **kwargs: meme_do_reddit())
    assert main(["--simular"]) == 0
    saida = capsys.readouterr().out
    assert "r/eu_nvr" in saida and "r/dankmemes" in saida  # tabela de diagnóstico das fontes
    corpo = json.loads(saida[saida.index("{", saida.index("🧪")) :])
    assert corpo["embeds"][0]["image"]["url"] == "https://i.redd.it/abc.png"
