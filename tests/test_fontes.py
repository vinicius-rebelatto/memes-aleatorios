import random
from dataclasses import replace

import pytest
import requests
from conftest import RespostaFalsa, RngFixo, SessaoFalsa, SessaoPorSubreddit, item_da_api, resposta_da_api

from bot.config import Fonte
from bot.fontes import (
    LIMITE_DE_UPLOAD,
    ErroDeFonte,
    baixar_imagem,
    buscar_memes,
    escolher_do_estoque,
    escolher_do_reddit,
    escolher_meme,
    id_do_post,
    ordem_das_fontes,
    titulo_util,
)
from bot.termometro import Termometro

nunca_postado = lambda meme: False
calado = lambda *_: None


def test_buscar_memes_tira_spoiler_e_o_que_nao_eh_imagem_mas_marca_nsfw():
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
    assert [m.link for m in memes] == ["https://redd.it/post1", "https://redd.it/post2", "https://redd.it/post5"]
    assert [m.nsfw for m in memes] == [False, True, False]
    assert memes[0].fonte == "reddit"
    assert memes[0].votos_reddit == 10
    assert memes[0].id_reddit == int("post1", 36)
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
    ("link", "esperado"),
    [
        ("https://redd.it/1y1vo6o", int("1y1vo6o", 36)),
        ("https://www.reddit.com/r/eu_nvr/comments/1xvr434/titulo/", int("1xvr434", 36)),
        ("https://i.redd.it/t20djbawjyw91.png", None),  # link de imagem não é link de post
        ("", None),
    ],
)
def test_id_do_post(link, esperado):
    assert id_do_post(link) == esperado


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
    meme = escolher_do_reddit(config, ja_postado, RngFixo(), sessao, log=calado)
    assert meme.link == "https://redd.it/post3"
    assert meme.nivel == 4  # nível da fonte r/eu_nvr


def test_meme_do_momento_ganha_de_meme_velho_com_mais_votos(config):
    sessao = SessaoPorSubreddit(
        {
            "eu_nvr": resposta_da_api(
                item_da_api(1, ups=2978, post="yhgfd4"),  # fixado de 2022: fica de fora
                item_da_api(2, ups=400, post="1xvr434"),  # ~1 semana: vale bem menos
                item_da_api(3, ups=100, post="1y1vo6o"),  # de hoje
            )
        }
    )
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=calado)
    assert meme.link == "https://redd.it/1y1vo6o"


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
    assert escolher_do_reddit(config, lambda meme: True, RngFixo(), sessao, log=calado) is None


def test_a_regua_puxa_as_fontes_com_nivel_mais_perto(config, tmp_path):
    sessao = SessaoPorSubreddit(
        {"eu_nvr": resposta_da_api(item_da_api(1)), "me_irl": resposta_da_api(item_da_api(2, subreddit="me_irl"))}
    )
    leve = Termometro(tmp_path / "t.json", regua=2.0)  # perto de me_irl (3), longe de eu_nvr (4)
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=calado, termometro=leve)
    assert meme.subreddit == "me_irl"


def test_post_surpresa_ignora_a_regua(config, tmp_path):
    config = replace(config, surpresa=1.0)
    sessao = SessaoPorSubreddit({"eu_nvr": resposta_da_api(item_da_api(1)), "me_irl": resposta_da_api()})
    avisos = []
    leve = Termometro(tmp_path / "t.json", regua=1.0)
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=avisos.append, termometro=leve)
    assert meme.subreddit == "eu_nvr"  # peso base maior, mesmo longe da régua
    assert "surpresa" in avisos[0]


def test_nsfw_so_entra_quando_permitido_e_conta_como_mais_pesado(config, tmp_path):
    def sessao():
        return SessaoPorSubreddit(
            {
                "eu_nvr": resposta_da_api(item_da_api(1, ups=10), item_da_api(2, ups=10, nsfw=True)),
                "me_irl": resposta_da_api(),
            }
        )

    # não permitido: nem entra na disputa
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao(), log=calado, permitir_nsfw=False)
    assert not meme.nsfw

    # permitido e com a régua no máximo: o NSFW (nível 4 + 1) é o mais perto
    pesada = Termometro(tmp_path / "a.json", regua=5.0)
    meme = escolher_do_reddit(
        config, nunca_postado, RngFixo(), sessao(), log=calado, termometro=pesada, permitir_nsfw=True
    )
    assert meme.nsfw and meme.nivel == 5

    # permitido, mas com a régua no meio: o meme comum fica mais perto
    media = Termometro(tmp_path / "b.json", regua=3.0)
    meme = escolher_do_reddit(
        config, nunca_postado, RngFixo(), sessao(), log=calado, termometro=media, permitir_nsfw=True
    )
    assert not meme.nsfw


def test_meme_de_fonte_fora_da_regua_nao_tem_nivel(config, tmp_path):
    config = replace(config, fontes=(Fonte("MinecraftMemes", peso=0.5),))
    sessao = SessaoPorSubreddit({"MinecraftMemes": resposta_da_api(item_da_api(1, subreddit="MinecraftMemes"))})
    pesada = Termometro(tmp_path / "t.json", regua=5.0)
    meme = escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=calado, termometro=pesada)
    assert meme.subreddit == "MinecraftMemes" and meme.nivel is None


def test_post_surpresa_ainda_respeita_os_votos_da_galera(config, tmp_path):
    config = replace(config, surpresa=1.0)
    sessao = SessaoPorSubreddit({"eu_nvr": resposta_da_api(), "me_irl": resposta_da_api(item_da_api(1))})
    # eu_nvr tem peso 3, mas levou muito 😐: na surpresa, me_irl vem primeiro
    termometro = Termometro(tmp_path / "t.json", afinidade={"eu_nvr": -3.0})
    escolher_do_reddit(config, nunca_postado, RngFixo(), sessao, log=calado, termometro=termometro)
    assert sessao.pedidos[0] == "me_irl"


class SessaoDeImagem:
    def __init__(self, resposta):
        self.resposta = resposta
        self.urls = []

    def get(self, url, **opcoes):
        self.urls.append(url)
        if isinstance(self.resposta, Exception):
            raise self.resposta
        return self.resposta


def imagem(status=200, conteudo=b"png", tipo="image/png"):
    resposta = RespostaFalsa(status, headers={"Content-Type": tipo})
    resposta.content = conteudo
    return resposta


def test_baixar_imagem_devolve_os_bytes():
    sessao = SessaoDeImagem(imagem())
    assert baixar_imagem("https://i.redd.it/a.png", sessao) == b"png"
    assert sessao.urls == ["https://i.redd.it/a.png"]


@pytest.mark.parametrize(
    "resposta",
    [
        imagem(status=404),
        imagem(tipo="text/html; charset=utf-8", conteudo=b"<html>removido</html>"),
        imagem(conteudo=b""),
        imagem(conteudo=b"x" * (LIMITE_DE_UPLOAD + 1)),
        requests.ConnectionError("sem rede"),
    ],
)
def test_baixar_imagem_falha_sem_derrubar_nada(resposta):
    assert baixar_imagem("https://i.redd.it/a.png", SessaoDeImagem(resposta)) is None


def test_ordem_das_fontes_respeita_os_pesos():
    fontes = (Fonte("pesado", peso=3), Fonte("leve", peso=1))
    pesos = {"pesado": 3, "leve": 1}
    rng = random.Random(42)
    primeiras = [ordem_das_fontes(fontes, pesos, rng)[0].subreddit for _ in range(4000)]
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
    meme = escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=calado)
    assert meme.fonte == "estoque"


def test_com_chance_o_estoque_vem_primeiro(config):
    (config.estoque_pasta / "meme.png").write_bytes(b"png")
    config = replace(config, estoque_chance=1.0)
    sessao = SessaoPorSubreddit({})
    meme = escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=calado)
    assert meme.fonte == "estoque"
    assert sessao.pedidos == []  # nem chegou a consultar o Reddit


def test_sem_estoque_e_sem_reddit_nao_ha_meme(config):
    sessao = SessaoPorSubreddit({"eu_nvr": requests.Timeout(), "me_irl": requests.Timeout()})
    assert escolher_meme(config, nunca_postado, RngFixo(0.5), sessao, log=calado) is None
