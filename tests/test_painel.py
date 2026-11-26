import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.fontes import Meme
from bot.historico import Historico
from bot.painel import montar_painel, salvar_painel
from bot.termometro import Termometro

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 22, 21, 3, tzinfo=BRT)


def registrar(historico, numero, dias_atras, fonte="reddit"):
    meme = Meme(fonte=fonte, chave=f"https://redd.it/p{numero}", link=f"https://redd.it/p{numero}", subreddit="eu_nvr")
    if fonte == "estoque":
        meme = Meme(fonte="estoque", chave=f"estoque/{numero}.png")
    historico.registrar(meme, str(1000 + numero), AGORA - timedelta(days=dias_atras))


def test_painel_resume_regua_chances_e_memes_recentes(config, tmp_path):
    evolucao = [{"quando": "2026-11-15T21:00:00-03:00", "regua": 3.0}]
    termometro = Termometro(
        tmp_path / "t.json", regua=4.0, afinidade={"eu_nvr": 0.5, "ShitpostBR": -1.0}, evolucao=evolucao
    )
    historico = Historico(tmp_path / "h.json")
    registrar(historico, 1, dias_atras=5)  # antigo: o /meme já pode repetir
    registrar(historico, 2, dias_atras=1)
    registrar(historico, 3, dias_atras=0.1, fonte="estoque")

    painel = montar_painel(config, termometro, historico, AGORA)

    assert painel["atualizado_em"] == "2026-11-22T21:03:00-03:00"
    assert (painel["regua"], painel["regua_texto"]) == (4.0, "4,0/5 🟩🟩🟨🟧⬜")
    assert painel["regua_na_semana"] == "🌶️ subiu 1,0"
    assert [f["subreddit"] for f in painel["fontes"]] == ["eu_nvr", "me_irl"]  # mais chance primeiro
    assert sum(f["chance"] for f in painel["fontes"]) == pytest.approx(1.0, abs=1e-3)
    # eu_nvr: nível 4 (na régua), peso 3 e 😂 (afinidade 0,5); me_irl: nível 3, peso 1
    assert painel["fontes"][0]["subreddit"] == "eu_nvr" and painel["fontes"][0]["chance"] > 0.85
    assert (painel["em_alta"], painel["em_baixa"]) == (["eu_nvr"], [])  # ShitpostBR saiu do config
    assert painel["recentes"] == ["https://redd.it/p2"]
    assert painel["reacoes"]["mais_pesado"] == "🌶️"
    assert (painel["ranking"], painel["votos_para_remover"]) == ("domingo às 21h", 3)


def test_salvar_painel_grava_json_legivel(config, tmp_path):
    caminho = tmp_path / "dados" / "painel.json"
    salvar_painel(caminho, {"regua_texto": "5,0/5 🟩🟩🟨🟧🟥"})
    assert "🟥" in caminho.read_text(encoding="utf-8")  # emoji gravado como emoji, não como \\u
    assert json.loads(caminho.read_text(encoding="utf-8")) == {"regua_texto": "5,0/5 🟩🟩🟨🟧🟥"}
