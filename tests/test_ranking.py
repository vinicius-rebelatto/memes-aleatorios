from datetime import datetime, timedelta, timezone

from conftest import reacao

from bot.fontes import Meme
from bot.historico import Historico
from bot.ranking import calcular_ranking, montar_anuncio
from bot.termometro import Termometro

BRT = timezone(timedelta(hours=-3))
FIM = datetime(2026, 11, 29, 21, 7, tzinfo=BRT)
INICIO = FIM - timedelta(days=7)
BOT = "999"


def preparar_historico(tmp_path):
    historico = Historico(tmp_path / "h.json")
    for id_mensagem, numero in (("1001", 1), ("1002", 2)):
        meme = Meme(
            fonte="reddit",
            chave=f"https://redd.it/p{numero}",
            imagem=f"https://i.redd.it/img{numero}.png",
            link=f"https://redd.it/p{numero}",
            subreddit="eu_nvr",
        )
        historico.registrar(meme, id_mensagem, INICIO)
    historico.registrar(
        Meme(fonte="estoque", chave="estoque/zoeira.png", arquivo=tmp_path / "zoeira.png"), "1003", INICIO
    )
    return historico


def mensagem(id_mensagem, autor, votos, do_bot=False, tipo=0, eh_bot=False):
    return {
        "id": id_mensagem,
        "type": tipo,
        "author": {"id": autor, "bot": eh_bot},
        "reactions": [reacao("😂", votos, do_bot=do_bot)] if votos else [],
    }


def mensagens_da_semana():
    return [
        mensagem("1001", BOT, 5, do_bot=True),  # meme do bot: 4 votos
        mensagem("1002", BOT, 3, do_bot=True),  # meme do bot: 2 votos
        mensagem("2001", "123", 4),  # meme da galera: 4 votos
        mensagem("1500", BOT, 9),  # anúncio antigo do bot: não concorre
        mensagem("2500", "777", 8, eh_bot=True),  # outro bot: não concorre
        mensagem("2600", "123", 6, tipo=7),  # mensagem de sistema: não concorre
        mensagem("2700", "456", 0),  # sem votos
    ]


def test_ranking_ordena_por_votos_e_desempata_por_quem_postou_antes(tmp_path):
    colocados = calcular_ranking(mensagens_da_semana(), BOT, preparar_historico(tmp_path), "😂")
    assert [(c.mensagem_id, c.votos) for c in colocados] == [("1001", 4), ("2001", 4), ("1002", 2)]
    assert colocados[0].registro["subreddit"] == "eu_nvr"
    assert colocados[1].registro is None


def test_ranking_pode_ignorar_posts_da_galera(tmp_path):
    colocados = calcular_ranking(
        mensagens_da_semana(), BOT, preparar_historico(tmp_path), "😂", incluir_galera=False, quantidade=5
    )
    assert [c.mensagem_id for c in colocados] == ["1001", "1002"]


def test_anuncio_mostra_o_podio_com_links_e_a_imagem_do_vencedor(tmp_path):
    colocados = calcular_ranking(mensagens_da_semana(), BOT, preparar_historico(tmp_path), "😂")
    corpo, anexo = montar_anuncio(colocados, "111", "555", "😂", INICIO, FIM, tmp_path)
    embed = corpo["embeds"][0]
    linhas = embed["description"].splitlines()
    assert linhas[0] == "🥇 **4 votos** — [meme do r/eu_nvr](https://discord.com/channels/111/555/1001)"
    assert linhas[1] == "🥈 **4 votos** — [meme de <@123>](https://discord.com/channels/111/555/2001)"
    assert linhas[2].startswith("🥉 **2 votos**")
    assert embed["image"] == {"url": "https://i.redd.it/img1.png"}
    assert embed["footer"]["text"].startswith("Votação de 22/11 a 29/11")
    assert corpo["allowed_mentions"] == {"parse": []}
    assert anexo is None


def test_vencedor_do_estoque_vai_como_arquivo(tmp_path):
    (tmp_path / "zoeira.png").write_bytes(b"png")
    historico = preparar_historico(tmp_path)
    colocados = calcular_ranking([mensagem("1003", BOT, 3, do_bot=True)], BOT, historico, "😂")
    corpo, anexo = montar_anuncio(colocados, "111", "555", "😂", INICIO, FIM, tmp_path)
    assert anexo == ("vencedor.png", b"png", "image/png")
    assert corpo["embeds"][0]["image"] == {"url": "attachment://vencedor.png"}
    assert corpo["attachments"] == [{"id": 0, "filename": "vencedor.png"}]


def test_semana_sem_votos_ganha_um_aviso(tmp_path):
    corpo, anexo = montar_anuncio([], "111", "555", "😂", INICIO, FIM, tmp_path)
    embed = corpo["embeds"][0]
    assert "Ninguém votou" in embed["description"]
    assert "image" not in embed and "fields" not in embed
    assert anexo is None


def test_anuncio_mostra_o_termometro_da_semana(tmp_path):
    evolucao = [
        {"quando": "2026-11-20T11:17:00-03:00", "regua": 3.0},
        {"quando": "2026-11-28T21:17:00-03:00", "regua": 3.45},
    ]
    termometro = Termometro(
        tmp_path / "t.json", regua=3.45, afinidade={"HUEstation": 1.25, "dankmemes": -0.5}, evolucao=evolucao
    )
    corpo, _ = montar_anuncio([], "111", "555", "😂", INICIO, FIM, tmp_path, termometro)
    campo = corpo["embeds"][0]["fields"][0]
    assert campo["name"] == "🌡️ Termômetro da galera"
    assert campo["value"].splitlines() == [
        "Régua: **3,5/5 🟩🟩🟨⬜⬜** (🌶️ subiu 0,5 na semana)",
        "Em alta: r/HUEstation",
        "Em baixa: r/dankmemes",
    ]
