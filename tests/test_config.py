from datetime import time, timedelta

import pytest

from bot.config import ErroDeConfiguracao, SegredosAusentes, carregar_config, ler_segredos


def test_config_do_repositorio_carrega():
    # só confere que o config.yml é válido: mudar fontes e horários não deve quebrar os testes
    config = carregar_config()
    assert config.fontes and config.horarios
    assert all(fonte.nivel is None or 1 <= fonte.nivel <= 5 for fonte in config.fontes)
    assert len({fonte.subreddit.lower() for fonte in config.fontes}) == len(config.fontes)  # sem repetidas
    assert len(set(config.reacoes.em_ordem())) == 4
    assert 1 <= config.regua_inicial <= 5
    assert config.estoque_pasta.name == "estoque"
    assert (config.historico.name, config.termometro.name, config.painel.name) == (
        "historico.json",
        "termometro.json",
        "painel.json",
    )


def test_horarios_do_repositorio_entre_aspas_e_sem_aspas_dao_no_mesmo(tmp_path):
    caminho = tmp_path / "config.yml"
    caminho.write_text(
        'fontes: [memes]\nagenda:\n  horarios: [\n      "09:00", 10:00,\n      "00:00", "02:00"\n    ]\n',
        encoding="utf-8",
    )
    config = carregar_config(caminho)
    assert config.horarios == (time(0), time(2), time(9), time(10))
    assert config.tolerancia == timedelta(hours=2)
    assert (config.ranking_dia, config.ranking_horario) == (6, time(21))


def test_fontes_aceitam_texto_simples_e_prefixo_r(tmp_path):
    caminho = tmp_path / "config.yml"
    caminho.write_text("fontes:\n  - r/memes\n  - subreddit: eu_nvr\n    peso: 2\n    nivel: 4\n", encoding="utf-8")
    config = carregar_config(caminho)
    assert [(f.subreddit, f.nivel, f.peso) for f in config.fontes] == [("memes", None, 1.0), ("eu_nvr", 4.0, 2.0)]
    assert not config.fontes[0].segue_a_regua  # sem nível: fora da régua
    assert config.fontes[1].segue_a_regua
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


def test_horarios_aceitam_varios_jeitos_de_escrever(tmp_path):
    caminho = tmp_path / "config.yml"
    # 12:00 sem aspas vira o número 720 no YAML: o bot entende mesmo assim
    caminho.write_text(
        'fontes: [memes]\nagenda:\n  horarios: ["21h30", 12:00, "9h", 7, "09:00"]\n  tolerancia_minutos: 45\n'
        "ranking:\n  dia: Sábado\n  horario: 20h\n",
        encoding="utf-8",
    )
    config = carregar_config(caminho)
    assert config.horarios == (time(7), time(9), time(12), time(21, 30))  # ordenados e sem repetição
    assert config.tolerancia == timedelta(minutes=45)
    assert (config.ranking_dia, config.ranking_horario) == (5, time(20))


@pytest.mark.parametrize(
    "conteudo",
    [
        'fontes: [memes]\nagenda:\n  horarios: ["25:00"]\n',
        'fontes: [memes]\nagenda:\n  horarios: ["meio-dia"]\n',
        "fontes: [memes]\nagenda:\n  horarios: []\n",
        'fontes: [memes]\nagenda:\n  horarios: ["09:00"]\n  tolerancia_minutos: 0\n',
        "fontes: [memes]\nranking:\n  dia: dia-de-folga\n",
    ],
)
def test_agenda_invalida_explica_o_erro(tmp_path, conteudo):
    caminho = tmp_path / "config.yml"
    caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ErroDeConfiguracao):
        carregar_config(caminho)


def test_dia_da_semana_com_feira_e_sem_acento(tmp_path):
    caminho = tmp_path / "config.yml"
    caminho.write_text("fontes: [memes]\nranking:\n  dia: terca-feira\n", encoding="utf-8")
    assert carregar_config(caminho).ranking_dia == 1
