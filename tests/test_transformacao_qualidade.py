from datetime import date

import numpy as np
import pandas as pd

from bcb_pipeline.analise import acumulado_12m
from bcb_pipeline.config import serie
from bcb_pipeline.qualidade import (
    Status,
    check_atualidade,
    check_lacunas_mensais,
    check_outliers,
    check_reconciliacao_ipca,
    lote_aprovado,
    validar_lote,
)
from bcb_pipeline.transformacao import dimensao_tempo, para_numero, transformar


def _bruto(pares):
    return pd.DataFrame(pares, columns=["data", "valor"])


def test_para_numero_aceita_ponto_virgula_e_invalidos():
    s = para_numero(pd.Series(["5.25", "1.234,56", "0,16", "", "abc", None]))
    assert s.iloc[:3].tolist() == [5.25, 1234.56, 0.16]
    assert s.iloc[3:].isna().all()


def test_transformar_tipa_e_ordena():
    df = transformar(_bruto([("01/02/2026", "0.70"), ("01/01/2026", "0.16")]), serie("ipca"))
    assert df["data"].is_monotonic_increasing
    assert df["valor"].dtype == "float64"
    assert (df["codigo_bcb"] == "433").all()


def test_transformar_vazio_mantem_esquema():
    df = transformar(pd.DataFrame(columns=["data", "valor"]), serie("ipca"))
    assert list(df.columns) == ["codigo_bcb", "data", "valor"] and df.empty


def test_dimensao_tempo_em_portugues():
    d = dimensao_tempo(pd.Series(pd.to_datetime(["2026-11-11", "2026-11-30", "2026-11-11"])))
    assert len(d) == 2
    assert d.iloc[0]["dia_semana"] == "quarta-feira"
    assert bool(d.iloc[1]["fim_de_mes"]) is True


def test_lote_valido_e_aprovado(ipca_mensal):
    df = pd.DataFrame({"codigo_bcb": "433", "data": ipca_mensal.index, "valor": ipca_mensal.values})
    res = validar_lote(df, serie("ipca"), incremental=False, hoje=date(2026, 10, 20))
    assert lote_aprovado(res), [r for r in res if r.status is not Status.OK]


def test_valor_fora_da_faixa_bloqueia_lote():
    df = transformar(_bruto([("01/01/2026", "0.16"), ("01/02/2026", "160.0")]), serie("ipca"))
    res = validar_lote(df, serie("ipca"), incremental=True, hoje=date(2026, 3, 1))
    bloqueantes = [r.checagem for r in res if r.status is Status.BLOQUEANTE]
    assert bloqueantes == ["faixa_valida"] and not lote_aprovado(res)


def test_valor_nao_numerico_bloqueia_lote():
    df = transformar(_bruto([("01/01/2026", "abc")]), serie("ipca"))
    res = validar_lote(df, serie("ipca"), incremental=True, hoje=date(2026, 2, 1))
    assert "sem_nulos" in [r.checagem for r in res if r.status is Status.BLOQUEANTE]


def test_incremental_sem_dados_novos_nao_e_bloqueante():
    df = transformar(pd.DataFrame(columns=["data", "valor"]), serie("ipca"))
    hist = pd.DataFrame({"data": [pd.Timestamp("2026-09-01")], "valor": [0.4]})
    res = validar_lote(df, serie("ipca"), incremental=True, historico=hist, hoje=date(2026, 10, 20))
    assert lote_aprovado(res)


def test_atualidade_e_informativa_quando_atrasada():
    r = check_atualidade(date(2026, 1, 1), serie("selic"), date(2026, 1, 20))
    assert r.status is Status.INFORMATIVO and r.valor_observado == 19


def test_lacuna_mensal_detectada(ipca_mensal):
    s = ipca_mensal.drop(pd.Timestamp("2020-05-01"))
    df = pd.DataFrame({"data": s.index, "valor": s.values})
    r = check_lacunas_mensais(df, serie("ipca"))
    assert r.status is Status.INFORMATIVO and "05/2020" in r.detalhe


def test_outlier_recente_detectado(ipca_mensal):
    s = ipca_mensal.copy()
    s.iloc[-3] = 9.0
    r = check_outliers(pd.DataFrame({"data": s.index, "valor": s.values}), serie("ipca"))
    assert r.status is Status.INFORMATIVO


def test_reconciliacao_ipca(ipca_mensal):
    mensal = pd.DataFrame({"data": ipca_mensal.index, "valor": ipca_mensal.values})
    oficial = acumulado_12m(ipca_mensal).round(2).dropna()
    oficial_df = pd.DataFrame({"data": oficial.index, "valor": oficial.values})
    assert check_reconciliacao_ipca(mensal, oficial_df, serie("ipca_12m")).status is Status.OK

    corrompido = mensal.copy()
    corrompido.loc[corrompido.index[-5], "valor"] += 0.5
    r = check_reconciliacao_ipca(corrompido, oficial_df, serie("ipca_12m"))
    assert r.status is Status.BLOQUEANTE and r.valor_observado > 0.4


def test_acumulado_12m_composto():
    s = pd.Series([1.0] * 12, index=pd.date_range("2020-01-01", periods=12, freq="MS"))
    assert np.isclose(acumulado_12m(s).iloc[-1], (1.01**12 - 1) * 100)
