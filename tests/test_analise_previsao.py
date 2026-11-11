import numpy as np
import pandas as pd
import pytest

from bcb_pipeline.analise import juro_real_ex_post, painel_mensal, para_mensal, resumo_indicador
from bcb_pipeline.previsao import HORIZONTE, backtest, ingenuo_sazonal, media_sazonal, prever_ipca


def test_juro_real_fisher():
    idx = pd.to_datetime(["2026-01-01"])
    r = juro_real_ex_post(pd.Series([15.0], idx), pd.Series([5.0], idx))
    assert np.isclose(r.iloc[0], (1.15 / 1.05 - 1) * 100)


def test_para_mensal_ultimo_e_media():
    idx = pd.to_datetime(["2026-01-02", "2026-01-30", "2026-02-02"])
    s = pd.Series([10.0, 12.0, 13.0], idx)
    assert para_mensal(s, "ultimo").tolist() == [12.0, 13.0]
    assert para_mensal(s, "media").tolist() == [11.0, 13.0]
    assert para_mensal(s).index[0] == pd.Timestamp("2026-01-01")


def test_painel_mensal_calcula_juro_real(ipca_mensal):
    selic = pd.Series(10.0, index=pd.date_range("2000-01-03", "2026-09-30", freq="B"))
    p = painel_mensal({"selic": selic, "ipca": ipca_mensal})
    assert {"selic", "ipca_12m", "juro_real", "ipca_ano"} <= set(p.columns)
    assert p["juro_real"].dropna().between(-10, 15).all()


def test_resumo_indicador(ipca_mensal):
    r = resumo_indicador(ipca_mensal, "mensal")
    assert r["data"] == "2026-09-01" and r["observacoes"] == len(ipca_mensal)
    assert r["valor_12m_atras"] == ipca_mensal.loc["2025-09-01"]


def test_baselines_tem_horizonte_certo(ipca_mensal):
    assert len(ingenuo_sazonal(ipca_mensal, 12)) == 12
    assert np.array_equal(ingenuo_sazonal(ipca_mensal, 12), ipca_mensal.iloc[-12:].to_numpy())
    assert np.isfinite(media_sazonal(ipca_mensal, 12)).all()


def test_backtest_sem_vazamento(ipca_mensal):
    erros = backtest(ipca_mensal, n_origens=6, modelos={"ingenuo_sazonal": ingenuo_sazonal})
    # toda previsão é para depois da origem e no máximo 12 meses à frente
    assert (erros["data"] > erros["origem"]).all()
    assert erros["horizonte"].between(1, HORIZONTE).all()
    # ingênuo sazonal no horizonte k == valor de 12 meses antes do alvo
    linha = erros.iloc[0]
    assert linha["previsto"] == ipca_mensal.loc[linha["data"] - pd.DateOffset(months=12)]


def test_backtest_historico_insuficiente():
    curto = pd.Series(0.4, index=pd.date_range("2020-01-01", periods=50, freq="MS"))
    with pytest.raises(ValueError):
        backtest(curto)


def test_prever_ipca_ponta_a_ponta(ipca_mensal):
    r = prever_ipca(ipca_mensal, n_origens=12)
    p = r.previsao
    assert len(p) == 12 and p["data"].iloc[0] == pd.Timestamp("2026-10-01")
    assert (p["li"] <= p["previsto"]).all() and (p["previsto"] <= p["ls"]).all()
    assert (p["li_12m"] <= p["ls_12m"]).all()
    assert set(r.metricas["modelo"]) == {"ingenuo_sazonal", "media_sazonal", "ridge_lags", "gbm_lags"}
    assert r.modelo_escolhido == r.metricas.iloc[0]["modelo"]
    # num AR(1) sazonal, algum modelo deve bater o ingênuo sazonal
    assert r.metricas["skill"].max() > 0
    assert 0.5 < r.cobertura_intervalo <= 1.0
