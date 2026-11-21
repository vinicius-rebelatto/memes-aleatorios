import pytest

from bot.config import ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos


def test_config_do_repositorio_carrega():
    config = carregar_config()
    niveis = {fonte.subreddit: fonte.nivel for fonte in config.fontes}
    assert niveis == {
        "wholesomememes": 1,
        "DiretoDoZapZap": 2,
        "HUEstation": 3,
        "me_irl": 3,
        "eu_nvr": 4,
        "dankmemes": 5,
    }
    assert config.reacoes.em_ordem() == ("😂", "😐", "🌶️", "🚫")
    assert config.regua_inicial == 3
    assert config.permitir_nsfw is True
    assert config.votos_para_remover == 3
    assert config.estoque_pasta.name == "estoque"
    assert config.historico.name == "historico.json"
    assert config.termometro.name == "termometro.json"


def test_fontes_aceitam_texto_simples_e_prefixo_r(tmp_path):
    caminho = tmp_path / "config.yml"
    caminho.write_text("fontes:\n  - r/memes\n  - subreddit: eu_nvr\n    peso: 2\n    nivel: 4\n", encoding="utf-8")
    config = carregar_config(caminho)
    assert [(f.subreddit, f.nivel, f.peso) for f in config.fontes] == [("memes", 3.0, 1.0), ("eu_nvr", 4.0, 2.0)]
    assert config.estoque_chance == 0.2  # valores padrão
    assert config.surpresa == 0.2
    assert config.reacoes.mais_pesado == "🌶️"


@pytest.mark.parametrize(
    "conteudo",
    [
        "fontes: []\n",
        "fontes:\n  - subreddit: memes\n    peso: 0\n",
        "fontes:\n  - memes\nestoque:\n  chance: 5\n",
        "fontes:\n  - memes\nmoderacao:\n  votos_para_remover: zero\n",
        "fontes: [memes\n",
        "fontes:\n  - subreddit: memes\n    nivel: 6\n",
        "fontes:\n  - memes\ntermometro:\n  regua_inicial: 0\n",
        "fontes:\n  - memes\ntermometro:\n  surpresa: 2\n",
        'fontes:\n  - memes\nreacoes:\n  engracado: "😂"\n  sem_graca: "😂"\n',
        'fontes:\n  - memes\nreacoes:\n  mais_pesado: ""\n',
    ],
)
def test_config_invalida_explica_o_erro(tmp_path, conteudo):
    caminho = tmp_path / "config.yml"
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ErroDeConfiguracao):
        carregar_config(caminho)


def test_ler_segredos_limpa_espacos_aspas_e_prefixo_bot():
    token, canal = ler_segredos({"DISCORD_TOKEN": ' "Bot abc.def" ', "DISCORD_CHANNEL_ID": " 123456 "})
    assert (token, canal) == ("abc.def", "123456")


def test_sem_nenhum_segredo_eh_so_um_aviso():
    with pytest.raises(SegredosAusentes):
        ler_segredos({})


def test_falta_um_segredo_eh_erro():
    with pytest.raises(ErroDeConfiguracao) as erro:
        ler_segredos({"DISCORD_TOKEN": "abc"})
    assert not isinstance(erro.value, SegredosAusentes)
    assert "DISCORD_CHANNEL_ID" in str(erro.value)


def test_nome_do_canal_no_lugar_do_id_eh_erro():
    with pytest.raises(ErroDeConfiguracao, match="só números"):
        ler_segredos({"DISCORD_TOKEN": "abc", "DISCORD_CHANNEL_ID": "memes-aleatorios"})
