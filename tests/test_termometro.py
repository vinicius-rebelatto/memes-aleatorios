from datetime import datetime, timedelta, timezone

import pytest
from conftest import reacoes_do_bot, snowflake

from bot.config import Fonte, Reacoes
from bot.fontes import Meme
from bot.historico import Historico
from bot.termometro import Termometro, barra, proximidade

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 22, 16, 17, tzinfo=BRT)
REACOES = Reacoes()


def id_de_horas_atras(horas: float) -> str:
    return snowflake(int((AGORA - timedelta(hours=horas)).timestamp() * 1000))


def historico_com(tmp_path, *memes):
    """memes = pares (id_da_mensagem, subreddit)."""
    historico = Historico(tmp_path / "h.json")
    for id_mensagem, subreddit in memes:
        meme = Meme(fonte="reddit", chave=f"https://redd.it/{id_mensagem}", subreddit=subreddit)
        historico.registrar(meme, id_mensagem, AGORA)
    return historico


def test_pimenta_sobe_a_regua_e_proibido_desce(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(mais_pesado=4)}, {}, REACOES)
    assert termometro.regua == pytest.approx(3.6)
    termometro.contar_votos({"id": "2", "reactions": reacoes_do_bot(passou_do_ponto=2)}, {}, REACOES)
    assert termometro.regua == pytest.approx(3.3)


def test_cada_voto_conta_uma_vez_so(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    mensagem = {"id": "1", "reactions": reacoes_do_bot(mais_pesado=2)}
    termometro.contar_votos(mensagem, {}, REACOES)
    termometro.contar_votos(mensagem, {}, REACOES)  # mesma leitura de novo
    assert termometro.regua == pytest.approx(3.3)
    # alguém tirou a pimenta: a régua volta um pouco
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(mais_pesado=1)}, {}, REACOES)
    assert termometro.regua == pytest.approx(3.15)


def test_engracado_e_sem_graca_mexem_na_afinidade_da_fonte(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    registro = {"fonte": "reddit", "subreddit": "eu_nvr"}
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(engracado=5, sem_graca=1)}, registro, REACOES)
    assert termometro.afinidade == {"eu_nvr": pytest.approx(1.4)}  # (5 - 1) x 0,35
    # meme do estoque não tem fonte do Reddit: não mexe na afinidade
    termometro.contar_votos({"id": "2", "reactions": reacoes_do_bot(engracado=3)}, {"fonte": "estoque"}, REACOES)
    assert list(termometro.afinidade) == ["eu_nvr"]


def test_regua_e_afinidade_tem_limites(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    registro = {"fonte": "reddit", "subreddit": "dankmemes"}
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(mais_pesado=50, sem_graca=50)}, registro, REACOES)
    assert termometro.regua == 5.0
    assert termometro.afinidade["dankmemes"] == -3.0


def test_atualizar_so_olha_memes_do_bot_dos_ultimos_dias(tmp_path):
    recente, antigo, da_galera = id_de_horas_atras(5), id_de_horas_atras(24 * 9), id_de_horas_atras(2)
    historico = historico_com(tmp_path, (recente, "eu_nvr"), (antigo, "me_irl"))
    termometro = Termometro(tmp_path / "t.json", votos_contados={antigo: {"engracado": 9}})
    mensagens = [
        {"id": recente, "reactions": reacoes_do_bot(engracado=2, mais_pesado=1)},
        {"id": antigo, "reactions": reacoes_do_bot(mais_pesado=10)},  # velho demais: ignora
        {"id": da_galera, "reactions": reacoes_do_bot(mais_pesado=10)},  # não é do bot: ignora
    ]
    assert termometro.atualizar(mensagens, historico, REACOES, AGORA)
    assert termometro.regua == pytest.approx(3.15)
    assert termometro.afinidade == {"eu_nvr": pytest.approx(0.7)}
    assert list(termometro.votos_contados) == [recente]  # o antigo saiu da conta
    assert termometro.evolucao == [{"quando": "2026-11-22T16:17:00-03:00", "regua": 3.15}]
    # nada novo na segunda leitura
    assert not termometro.atualizar(mensagens, historico, REACOES, AGORA)


def test_fonte_perto_da_regua_e_com_afinidade_ganha_mais_peso(tmp_path):
    termometro = Termometro(tmp_path / "t.json", regua=3.0)
    fontes = (Fonte("perto", nivel=3), Fonte("longe", nivel=5))
    pesos = termometro.pesos(fontes)
    assert pesos["perto"] > 3 * pesos["longe"]
    assert proximidade(4, 3) == pytest.approx(0.707, abs=0.01)
    termometro.afinidade["longe"] = 3.0  # muito 😂 compensa a distância
    assert termometro.pesos(fontes)["longe"] > termometro.pesos(fontes)["perto"]


def test_fonte_sem_nivel_fica_fora_da_regua_mas_segue_os_votos(tmp_path):
    fontes = (Fonte("pesada", nivel=5), Fonte("MinecraftMemes"))
    for regua in (1.0, 5.0):
        pesos = Termometro(tmp_path / "t.json", regua=regua).pesos(fontes)
        assert pesos["MinecraftMemes"] >= 0.5
    termometro = Termometro(tmp_path / "t.json", regua=5.0, afinidade={"MinecraftMemes": -2.0})
    assert termometro.pesos(fontes)["MinecraftMemes"] < 0.15  # 😐 derrubam até jogo


def test_post_surpresa_ignora_a_regua_mas_nao_os_votos(tmp_path):
    fontes = (Fonte("leve", nivel=1), Fonte("pesada", nivel=5), Fonte("chata", nivel=1))
    termometro = Termometro(tmp_path / "t.json", regua=5.0, afinidade={"chata": -3.0})
    assert termometro.pesos(fontes)["leve"] < 0.01  # longe da régua
    surpresa = termometro.pesos(fontes, surpresa=True)
    assert surpresa["leve"] == pytest.approx(surpresa["pesada"])
    assert surpresa["chata"] < 0.05


def test_categoria_sorteia_primeiro_e_dentro_dela_o_melhor_subreddit_se_sobressai(tmp_path):
    fontes = (
        Fonte("LeagueOfMemes", categoria="jogos"),
        Fonte("MinecraftMemes", categoria="jogos"),
        Fonte("dontstarve", categoria="jogos"),
        Fonte("memes", nivel=2, categoria="gerais"),
    )
    termometro = Termometro(tmp_path / "t.json", regua=2.0)
    pesos = termometro.pesos(fontes)
    assert pesos["memes"] == pytest.approx(0.5)  # 2 categorias meio a meio, mesmo com 3 subs em jogos
    assert pesos["LeagueOfMemes"] == pytest.approx(0.5 / 3)
    termometro.afinidade.update({"LeagueOfMemes": 1.5, "dontstarve": -2.0})
    pesos = termometro.pesos(fontes)
    assert pesos["LeagueOfMemes"] > 10 * pesos["dontstarve"]
    assert pesos["memes"] == pytest.approx(0.5)  # a categoria continua com a mesma fatia


def test_votos_tambem_dao_nota_para_a_categoria(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    registro = {"fonte": "reddit", "subreddit": "dontstarve", "categoria": "jogos"}
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(sem_graca=3)}, registro, REACOES)
    assert termometro.afinidade_categorias == {"jogos": pytest.approx(-0.45)}
    assert termometro.afinidade == {"dontstarve": pytest.approx(-1.05)}


def test_chances_juntam_posts_normais_e_surpresa(tmp_path):
    fontes = (Fonte("pesada", nivel=5), Fonte("leve", nivel=1), Fonte("jogo", peso=0.5))
    termometro = Termometro(tmp_path / "t.json", regua=5.0)
    chances = termometro.chances(fontes, surpresa=0.2)
    assert sum(chances.values()) == pytest.approx(1.0)
    normal, sorteio = termometro.pesos(fontes), termometro.pesos(fontes, surpresa=True)
    assert chances["leve"] == pytest.approx(0.8 * normal["leve"] + 0.2 * sorteio["leve"])
    assert sorteio == pytest.approx({"pesada": 0.4, "leve": 0.4, "jogo": 0.2})


def test_variacao_na_semana_e_desenho_da_regua(tmp_path):
    evolucao = [
        {"quando": "2026-11-10T11:17:00-03:00", "regua": 2.8},
        {"quando": "2026-11-15T16:17:00-03:00", "regua": 3.0},
        {"quando": "2026-11-20T21:17:00-03:00", "regua": 3.4},
    ]
    termometro = Termometro(tmp_path / "t.json", regua=3.4, evolucao=evolucao)
    assert termometro.variacao_desde(AGORA - timedelta(days=7)) == pytest.approx(0.4)
    assert termometro.variacao_desde(datetime(2026, 1, 1, tzinfo=BRT)) == pytest.approx(0.6)
    assert termometro.descrever_regua() == "3,4/5 🟩🟩🟨⬜⬜"
    assert barra(5) == "🟩🟩🟨🟧🟥"
    assert barra(1) == "🟩⬜⬜⬜⬜"


def test_fontes_em_alta_e_em_baixa(tmp_path):
    termometro = Termometro(tmp_path / "t.json", afinidade={"a": 1.5, "b": -0.5, "c": 0.0, "d": 0.25})
    assert termometro.fontes_em_destaque() == ([("a", 1.5), ("d", 0.25)], [("b", -0.5)])
    # fonte que saiu do config.yml não aparece mais
    assert termometro.fontes_em_destaque(fontes=(Fonte("a"), Fonte("c"))) == ([("a", 1.5)], [])


def test_salvar_e_carregar(tmp_path):
    caminho = tmp_path / "dados" / "termometro.json"
    termometro = Termometro.carregar(caminho, regua_inicial=2.0)
    assert termometro.regua == 2.0
    termometro.afinidade["eu_nvr"] = 0.75
    termometro.salvar()
    de_novo = Termometro.carregar(caminho, regua_inicial=4.0)  # o arquivo manda, não o padrão
    assert de_novo.regua == 2.0
    assert de_novo.afinidade == {"eu_nvr": 0.75}


def test_curti_conta_como_voto_positivo_para_a_fonte(tmp_path):
    termometro = Termometro(tmp_path / "t.json")
    registro = {"fonte": "reddit", "subreddit": "eu_nvr"}
    termometro.contar_votos({"id": "1", "reactions": reacoes_do_bot(curti=2, sem_graca=1)}, registro, REACOES)
    assert termometro.afinidade["eu_nvr"] == pytest.approx(0.35)  # 2 👍 - 1 😐
    assert termometro.regua == 3.0  # 👍 não mexe na régua
