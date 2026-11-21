import random
from dataclasses import replace

import pytest
import requests
from conftest import RespostaFalsa, RngFixo, SessaoFalsa, SessaoPorSubreddit, item_da_api, resposta_da_api

from bot.config import Fonte
from bot.fontes import (
    LIMITE_DE_UPLOAD,
    ErroDeFonte,
    buscar_memes,
    escolher_do_estoque,
    escolher_do_reddit,
    escolher_meme,
    ordem_das_fontes,
    titulo_util,
)

nunca_postado = lambda meme: False


def test_buscar_memes_filtra_nsfw_spoiler_e_o_que_nao_eh_imagem():
    sessao = SessaoFalsa(
        [
            resposta_da_api(
                item_da_api(1),
                item_da_api(2, nsfw=True),
                item_da_api(3, spoiler=True),
                item_da_api(4, url="https://v.redd.it/video4"),
                item_da_api(5, url="https://i.imgur.com/foto5.JPG?x=1"),
            )
        ]
    )
    memes = buscar_memes("eu_nvr", sessao)
    assert [m.link for m in memes] == ["https://redd.it/post1", "https://redd.it/post5"]
    assert memes[0].fonte == "reddit"
    assert memes[0].votos_reddit == 10
    _, url, _ = sessao.chamadas[0]
    assert url == "https://meme-api.com/gimme/eu_nvr/50"


def test_buscar_memes_aceita_resposta_com_um_meme_so():
    sessao = SessaoFalsa([RespostaFalsa(200, item_da_api(7, ups=3))])
    memes = buscar_memes("eu_nvr", sessao)
    assert len(memes) == 1 and memes[0].votos_reddit == 3


@pytest.mark.parametrize(
    "resposta",
    [
        RespostaFalsa(404, {"code": 404, "message": "This subreddit does not exist"}),
        RespostaFalsa(200, {"code": 400, "message": "r/fechado is private"}),
        RespostaFalsa(500, None),
    ],
)
def test_buscar_memes_falha_com_erro_claro(resposta):
    with pytest.raises(ErroDeFonte):
        buscar_memes("eu_nvr", SessaoFalsa([resposta]))


@pytest.mark.parametrize(
    ("titulo", "esperado"),
    [
        ("eu😐nvr", ""),
        ("Eu_nvr", ""),
        ("eu-nvr", ""),
        ("", ""),
        ("quando o CEO aparece no rolê", "quando o CEO aparece no rolê"),
    ],
)
def test_titulo_util_ignora_titulo_que_so_repete_o_subreddit(titulo, esperado):
    assert titulo_util(titulo, "eu_nvr") == esperado


def test_titulo_util_corta_titulos_longos():
    assert len(titulo_util("a" * 400, "eu_nvr")) == 256


def test_escolhe_o_mais_votado_que_ainda_nao_saiu(config):
    sessao = SessaoPorSubreddit(
        {"eu_nvr": resposta_da_api(item_da_api(1, ups=10), item_da_api(2, ups=50), item_da_api(3, ups=30))}
    )
    ja_postado = lambda meme: meme.link == "https://redd.it/post2"
    meme = escolher_do_reddit(config, ja_postado, RngFixo(), sessao, log=lambda *_: None)
    assert meme.link == "https://redd.it/post3"


def test_se_uma_fonte_falha_tenta_a_proxima(config):
    sessao = SessaoPorSubreddit(
        {
            "eu_nvr": requests.ConnectionError("fora do ar"),
            "me_irl": resposta_da_api(item_da_api(9, subreddit="me_irl")),
        }
    )
    avisos = []
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=avisos.append)
    assert sessao.pedidos == ["eu_nvr", "me_irl"]  # peso maior primeiro
    assert meme.subreddit == "me_irl"
    assert "r/eu_nvr" in avisos[0]


def test_se_tudo_ja_saiu_devolve_nada(config):
    sessao = SessaoPorSubreddit({"eu_nvr": resposta_da_api(item_da_api(1)), "me_irl": resposta_da_api()})
    assert escolher_do_reddit(config, lambda meme: True, RngFixo(), sessao, log=lambda *_: None) is None


def test_ordem_das_fontes_respeita_os_pesos():
    fontes = (Fonte("pesado", 3), Fonte("leve", 1))
    rng = random.Random(42)
    primeiras = [ordem_das_fontes(fontes, rng)[0].subreddit for _ in range(4000)]
    proporcao = primeiras.count("pesado") / len(primeiras)
    assert 0.71 < proporcao < 0.79  # peso 3 contra 1: ~75% das vezes vem primeiro


def test_estoque_ignora_o_que_nao_eh_imagem_ja_postado_e_grande_demais(config):
    pasta = config.estoque_pasta
    (pasta / "a.png").write_bytes(b"png")
    (pasta / "b.JPG").write_bytes(b"jpg")
    (pasta / "LEIA-ME.md").write_text("oi", encoding="utf-8")
    with open(pasta / "enorme.gif", "wb") as arquivo:
        arquivo.truncate(LIMITE_DE_UPLOAD + 1)
    avisos = []
    ja_postado = lambda meme: meme.chave == "estoque/a.png"
    meme = escolher_do_estoque(config, ja_postado, RngFixo(), log=avisos.append)
    assert meme.chave == "estoque/b.JPG"
    assert meme.fonte == "estoque"
    assert any("enorme.gif" in aviso for aviso in avisos)


def test_estoque_vira_plano_b_quando_o_reddit_falha(config):
    (config.estoque_pasta / "meme.png").write_bytes(b"png")
    sessao = SessaoPorSubreddit({"eu_nvr": requests.Timeout(), "me_irl": requests.Timeout()})
    meme = escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=lambda *_: None)
    assert meme.fonte == "estoque"


def test_com_chance_o_estoque_vem_primeiro(config):
    (config.estoque_pasta / "meme.png").write_bytes(b"png")
    config = replace(config, estoque_chance=1.0)
    sessao = SessaoPorSubreddit({})
    meme = escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=lambda *_: None)
    assert meme.fonte == "estoque"
    assert sessao.pedidos == []  # nem chegou a consultar o Reddit


def test_sem_estoque_e_sem_reddit_nao_ha_meme(config):
    sessao = SessaoPorSubreddit({"eu_nvr": requests.Timeout(), "me_irl": requests.Timeout()})
    assert escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=lambda *_: None) is None
