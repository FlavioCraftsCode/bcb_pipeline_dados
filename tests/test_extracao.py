from datetime import date

import pandas as pd
import pytest
import requests

from bcb_pipeline.config import Configuracoes, serie
from bcb_pipeline.extracao import ClienteSGS, ErroExtracao, data_inicio_incremental, gerar_janelas
from conftest import RespostaFalsa

CFG = Configuracoes(tentativas=3, backoff_inicial_segundos=0.01)


def test_janelas_cobrem_intervalo_sem_sobreposicao():
    ini, fim = pd.Timestamp("1980-01-01"), pd.Timestamp("2026-11-11")
    janelas = list(gerar_janelas(ini, fim, 10))
    assert janelas[0][0] == ini and janelas[-1][1] == fim
    for (_, b1), (a2, _) in zip(janelas, janelas[1:], strict=False):
        assert a2 - b1 == pd.Timedelta(days=1)
    assert all((b - a).days < 366 * 10 for a, b in janelas)


def test_janelas_vazias_quando_inicio_maior_que_fim():
    assert list(gerar_janelas(pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-01"), 10)) == []


def test_inicio_incremental_recua_periodos_de_revisao():
    ibc = serie("ibcbr")  # 24 meses de revisão
    assert data_inicio_incremental(ibc, date(2026, 8, 1)) == pd.Timestamp("2024-08-01")
    assert data_inicio_incremental(ibc, None) == pd.Timestamp("2003-01-01")


def test_inicio_incremental_nunca_antes_do_inicio_da_serie():
    s = serie("desemprego")
    assert data_inicio_incremental(s, date(2012, 4, 1)) == pd.Timestamp("2012-03-01")


def test_retry_em_erro_transitorio_e_sucesso(sessao_falsa):
    sessao = sessao_falsa(
        [
            RespostaFalsa(503),
            requests.ConnectionError("reset"),
            RespostaFalsa(200, [{"data": "01/01/2026", "valor": "0.16"}]),
        ]
    )
    esperas = []
    cliente = ClienteSGS(CFG, sessao=sessao, dormir=esperas.append)
    df = cliente.extrair(serie("ipca"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-31"))
    assert df.to_dict("records") == [{"data": "01/01/2026", "valor": "0.16"}]
    assert len(esperas) == 2 and esperas[1] > esperas[0]  # backoff exponencial
    assert cliente.estatisticas.tentativas_extras == 2


def test_erro_definitivo_falha_sem_retry(sessao_falsa):
    sessao = sessao_falsa([RespostaFalsa(406, texto="janela maior que 10 anos")])
    cliente = ClienteSGS(CFG, sessao=sessao, dormir=lambda _: None)
    with pytest.raises(ErroExtracao, match="406"):
        cliente.extrair(serie("ipca"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-31"))
    assert len(sessao.chamadas) == 1


def test_esgota_tentativas(sessao_falsa):
    sessao = sessao_falsa([RespostaFalsa(500)] * 3)
    cliente = ClienteSGS(CFG, sessao=sessao, dormir=lambda _: None)
    with pytest.raises(ErroExtracao, match="Esgotadas 3"):
        cliente.extrair(serie("ipca"), pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-31"))


def test_404_e_janela_vazia_e_deduplica_entre_janelas(sessao_falsa):
    sessao = sessao_falsa(
        [
            RespostaFalsa(404),
            RespostaFalsa(200, [{"data": "01/01/2010", "valor": "0.75"}, {"data": "01/02/2010", "valor": "0.78"}]),
            RespostaFalsa(200, [{"data": "01/02/2010", "valor": "0.79"}]),
        ]
    )
    cliente = ClienteSGS(CFG, sessao=sessao, dormir=lambda _: None)
    df = cliente.extrair(serie("ipca"), pd.Timestamp("1990-01-01"), pd.Timestamp("2019-12-31"))
    assert len(sessao.chamadas) == 3
    assert cliente.estatisticas.janelas_vazias == 1
    assert df.set_index("data")["valor"].to_dict() == {"01/01/2010": "0.75", "01/02/2010": "0.79"}
