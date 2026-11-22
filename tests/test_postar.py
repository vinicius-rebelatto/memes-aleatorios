import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import DiscordFalso, reacoes_do_bot, snowflake

import bot.postar as modulo_postar
from bot.discord_api import ErroDiscord
from bot.fontes import Meme
from bot.historico import Historico
from bot.postar import executar, main, montar_mensagem
from bot.termometro import Termometro

BRT = timezone(timedelta(hours=-3))
LEGENDA = "😂 engraçado · 😐 sem graça · 🌶️ mais pesado · 🚫 passou do ponto"
calado = lambda *_: None


def em(hora: int, minuto: int = 0, dia: int = 22) -> datetime:
    return datetime(2026, 11, dia, hora, minuto, tzinfo=BRT)  # 22/11/2026 é domingo


def meme_do_reddit(titulo="eu_nvr", nsfw=False, numero=1):
    return Meme(
        fonte="reddit",
        chave=f"https://redd.it/abc{numero}",
        titulo=titulo,
        imagem=f"https://i.redd.it/abc{numero}.png",
        link=f"https://redd.it/abc{numero}",
        subreddit="eu_nvr",
        votos_reddit=744,
        nsfw=nsfw,
        nivel=3,
    )


def rodar(config, tmp_path, modo, quando, discord=None, historico=None, termometro=None, escolher=None, log=calado):
    discord = discord or DiscordFalso()
    historico = historico or Historico(tmp_path / "h.json")
    termometro = termometro or Termometro(tmp_path / "t.json")
    escolher = escolher or meme_do_reddit
    resultado = executar(discord, config, historico, termometro, "555", modo, quando, escolher, log)
    return resultado, discord, historico, termometro


# ---- a mensagem ---------------------------------------------------------------------


def test_mensagem_do_reddit_tem_imagem_fonte_regua_e_legenda(config):
    corpo, anexo = montar_mensagem(meme_do_reddit(), config, regua=3.35)
    embed = corpo["embeds"][0]
    assert anexo is None
    assert embed["image"] == {"url": "https://i.redd.it/abc1.png"}
    assert embed["author"] == {"name": "r/eu_nvr", "url": "https://redd.it/abc1"}
    assert "title" not in embed  # o título só repetia o nome do subreddit
    assert embed["footer"]["text"] == f"⬆️ 744 no Reddit • 🌡️ régua 3,4/5 • {LEGENDA}"
    assert corpo["allowed_mentions"] == {"parse": []}


def test_titulo_informativo_aparece_e_nsfw_ganha_aviso(config):
    corpo, _ = montar_mensagem(meme_do_reddit("quando o deploy é sexta", nsfw=True), config)
    embed = corpo["embeds"][0]
    assert embed["title"] == "quando o deploy é sexta"
    assert embed["url"] == "https://redd.it/abc1"
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


# ---- modo agora (botão) --------------------------------------------------------------


def test_modo_agora_posta_com_as_4_reacoes_mesmo_fora_de_hora(config, tmp_path):
    resultado, discord, historico, _ = rodar(config, tmp_path, "agora", em(3, 0))
    assert len(discord.enviadas) == 1
    assert discord.reacoes == [("5001", "😂"), ("5001", "😐"), ("5001", "🌶️"), ("5001", "🚫")]
    assert discord.dormidas == [0.35, 0.35, 0.35]
    assert resultado.meme["id_mensagem"] == "5001"
    assert resultado.meme["postado_em"] == "2026-11-22T03:00:00-03:00"
    assert resultado.mudou_algo and not resultado.erros
    assert historico.ja_postado(meme_do_reddit())


# ---- modo agenda (relógio) -----------------------------------------------------------


def test_agenda_posta_dentro_da_janela_do_horario(config, tmp_path):
    avisos = []
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(12, 1), log=avisos.append)
    assert resultado.meme is not None
    assert "⏰ Hora do meme das 12h." in avisos


def test_agenda_nao_posta_duas_vezes_no_mesmo_horario(config, tmp_path):
    historico = Historico(tmp_path / "h.json")
    rodar(config, tmp_path, "agenda", em(12, 1), historico=historico)
    avisos = []
    contador = iter(range(2, 99))
    resultado, discord, _, _ = rodar(
        config,
        tmp_path,
        "agenda",
        em(12, 40),
        historico=historico,
        escolher=lambda: meme_do_reddit(numero=next(contador)),
        log=avisos.append,
    )
    assert resultado.meme is None and discord.enviadas == []
    assert "✅ O meme das 12h já saiu." in avisos
    assert not resultado.mudou_algo  # nada a salvar: não gera commit


def test_agenda_fora_de_hora_so_modera(config, tmp_path):
    avisos = []
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(3, 46), log=avisos.append)
    assert resultado.meme is None and discord.enviadas == []
    assert "⏰ Fora do horário de posts. Próximo: 9h." in avisos


def test_agenda_atrasada_demais_pula_o_horario(config, tmp_path):
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(11, 5))  # o das 9h venceu às 11h
    assert resultado.meme is None and discord.enviadas == []


def test_meme_da_semana_sai_no_domingo_depois_do_meme_das_21h_e_uma_vez_so(config, tmp_path):
    historico = Historico(tmp_path / "h.json")
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(21, 2), historico=historico)
    assert resultado.meme is not None and resultado.ranking
    assert discord.enviadas[1]["corpo"]["embeds"][0]["title"] == "🏆 Meme da Semana"
    # acordou de novo às 21h50: nem meme nem ranking repetidos
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(21, 50), historico=historico)
    assert resultado.meme is None and not resultado.ranking and discord.enviadas == []


def test_meme_da_semana_nao_sai_em_outro_dia(config, tmp_path):
    resultado, _, _, _ = rodar(config, tmp_path, "agenda", em(21, 2, dia=21))  # sábado
    assert resultado.meme is not None and not resultado.ranking


def test_modo_ranking_anuncia_na_hora_sem_postar_meme(config, tmp_path):
    resultado, discord, _, _ = rodar(config, tmp_path, "ranking", em(15, 0, dia=24))
    assert resultado.ranking and resultado.meme is None
    assert len(discord.enviadas) == 1


# ---- termômetro, moderação e problemas ------------------------------------------------


def registrar_meme_antigo(historico, quando, horas_atras):
    momento = quando - timedelta(hours=horas_atras)
    id_mensagem = snowflake(int(momento.timestamp() * 1000))
    historico.registrar(Meme(fonte="reddit", chave="x", subreddit="eu_nvr", link="x"), id_mensagem, momento)
    return id_mensagem


def test_votos_da_galera_mexem_na_regua_antes_do_post(config, tmp_path):
    quando = em(12, 1)
    historico = Historico(tmp_path / "h.json")
    anterior = registrar_meme_antigo(historico, quando, 3)
    discord = DiscordFalso([{"id": anterior, "reactions": reacoes_do_bot(engracado=1, mais_pesado=2)}])

    _, discord, _, termometro = rodar(config, tmp_path, "agenda", quando, discord=discord, historico=historico)

    assert termometro.regua == pytest.approx(3.3)
    assert termometro.afinidade == {"eu_nvr": pytest.approx(0.25)}
    rodape = discord.enviadas[0]["corpo"]["embeds"][0]["footer"]["text"]
    assert "🌡️ régua 3,3/5" in rodape


def test_meme_apagado_fora_de_hora_tambem_conta_como_mudanca(config, tmp_path):
    quando = em(3, 0)
    historico = Historico(tmp_path / "h.json")
    anterior = registrar_meme_antigo(historico, quando, 5)
    discord = DiscordFalso([{"id": anterior, "reactions": reacoes_do_bot(passou_do_ponto=3)}])
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", quando, discord=discord, historico=historico)
    assert discord.apagadas == [anterior]
    assert resultado.mudou_algo  # o termômetro mudou: precisa salvar


def test_nsfw_so_vale_em_canal_restrito_por_idade(config, tmp_path):
    avisos = []
    rodar(config, tmp_path, "agora", em(12), discord=DiscordFalso(canal_nsfw=False), log=avisos.append)
    assert any("restrito por idade" in aviso for aviso in avisos)
    avisos = []
    rodar(config, tmp_path, "agora", em(12), discord=DiscordFalso(canal_nsfw=True), log=avisos.append)
    assert not any("restrito por idade" in aviso for aviso in avisos)


def test_sem_meme_novo_vira_erro_sem_derrubar_o_resto(config, tmp_path):
    resultado, discord, _, _ = rodar(config, tmp_path, "agenda", em(21, 2), escolher=lambda: None)
    assert resultado.meme is None and resultado.erros
    assert resultado.ranking  # o Meme da Semana saiu mesmo assim
    assert len(discord.enviadas) == 1


def test_problema_ao_ler_ou_reagir_nao_impede_o_post(config, tmp_path):
    class DiscordMeioQuebrado(DiscordFalso):
        def mensagens_desde(self, *args, **kwargs):
            raise ErroDiscord(403, 50001, "Missing Access", "GET")

        def reagir(self, canal_id, mensagem_id, emoji):
            raise ErroDiscord(403, 50013, "Missing Permissions", "PUT")

    avisos = []
    resultado, discord, _, _ = rodar(
        config, tmp_path, "agora", em(12), discord=DiscordMeioQuebrado(), log=avisos.append
    )
    assert len(discord.enviadas) == 1 and resultado.meme is not None
    assert any("ler as reações" in aviso for aviso in avisos)
    assert sum("reagir" in aviso for aviso in avisos) == 4


# ---- linha de comando ------------------------------------------------------------------


def test_sem_secrets_o_bot_avisa_e_sai_sem_erro(monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main(["--modo", "agenda"]) == 0
    assert "ainda não foram configurados" in capsys.readouterr().out


def test_secret_errado_falha(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "abc")
    monkeypatch.setenv("DISCORD_CHANNEL_ID", "nome-do-canal")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert main([]) == 1


def test_modo_invalido_e_recusado():
    with pytest.raises(SystemExit):
        main(["--modo", "festa"])


def test_simular_testa_as_fontes_e_mostra_o_post_sem_usar_o_discord(monkeypatch, capsys):
    monkeypatch.setattr(modulo_postar, "buscar_memes", lambda subreddit: [meme_do_reddit()])
    monkeypatch.setattr(modulo_postar, "escolher_meme", lambda *args, **kwargs: meme_do_reddit())
    assert main(["--modo", "simular"]) == 0
    saida = capsys.readouterr().out
    assert "r/eu_nvr" in saida and "r/circojeca" in saida  # tabela de diagnóstico das fontes
    assert "⏰ Horários: 9h, 12h, 15h, 18h, 21h" in saida
    corpo = json.loads(saida[saida.index("{", saida.index("🧪")) :])
    assert corpo["embeds"][0]["image"]["url"] == "https://i.redd.it/abc1.png"
