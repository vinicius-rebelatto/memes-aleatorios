from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.fontes import Meme
from bot.historico import Historico

QUANDO = datetime(2026, 11, 21, 16, 17, tzinfo=timezone(timedelta(hours=-3)))


def meme_do_reddit(numero=1, imagem=None):
    return Meme(
        fonte="reddit",
        chave=f"https://redd.it/post{numero}",
        titulo="eu_nvr",
        imagem=imagem or f"https://i.redd.it/img{numero}.png",
        link=f"https://redd.it/post{numero}",
        subreddit="eu_nvr",
        votos_reddit=744,
    )


def test_arquivo_inexistente_ou_vazio_vira_historico_vazio(tmp_path):
    assert Historico.carregar(tmp_path / "nao-existe.json").memes == []
    vazio = tmp_path / "vazio.json"
    vazio.write_text("", encoding="utf-8")
    assert Historico.carregar(vazio).memes == []


def test_historico_inicial_do_repositorio_esta_vazio():
    raiz = Path(__file__).resolve().parent.parent
    assert Historico.carregar(raiz / "dados" / "historico.json").memes == []


def test_registrar_salvar_e_carregar_de_novo(tmp_path):
    caminho = tmp_path / "dados" / "historico.json"
    historico = Historico.carregar(caminho)
    registro = historico.registrar(meme_do_reddit(1), "123", QUANDO)
    assert registro["postado_em"] == "2026-11-21T16:17:00-03:00"
    assert "arquivo" not in registro  # campos vazios não são gravados
    historico.salvar()

    de_novo = Historico.carregar(caminho)
    assert de_novo.ja_postado(meme_do_reddit(1))
    assert not de_novo.ja_postado(meme_do_reddit(2))
    # mesmo meme repostado em outro post (mesma imagem) também conta como repetido
    assert de_novo.ja_postado(meme_do_reddit(3, imagem="https://i.redd.it/img1.png"))
    assert de_novo.por_mensagem("123")["subreddit"] == "eu_nvr"
    assert de_novo.ids_de_mensagens() == {"123"}


def test_meme_do_estoque_guarda_o_nome_do_arquivo(tmp_path):
    historico = Historico(tmp_path / "h.json")
    meme = Meme(fonte="estoque", chave="estoque/zoeira.png", arquivo=tmp_path / "zoeira.png")
    registro = historico.registrar(meme, "77", QUANDO)
    assert registro["arquivo"] == "zoeira.png"
    assert historico.ja_postado(Meme(fonte="estoque", chave="estoque/zoeira.png"))


def test_salvar_mantem_acentos_e_emojis_legiveis(tmp_path):
    caminho = tmp_path / "h.json"
    historico = Historico(caminho)
    meme = meme_do_reddit(1)
    meme.titulo = "Ação 😂"
    historico.registrar(meme, "1", QUANDO)
    historico.salvar()
    assert "Ação 😂" in caminho.read_text(encoding="utf-8")
