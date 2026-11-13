import pandas as pd
import pytest

from bcb_pipeline.analise import decisoes_selic, situacao_meta_inflacao


def _selic(valores: list[float], inicio: str = "2025-01-01") -> pd.Series:
    return pd.Series(valores, index=pd.date_range(inicio, periods=len(valores), freq="D"))


def test_decisoes_selic_detecta_mudancas_e_ordena_da_mais_recente():
    s = _selic([10.0, 10.0, 10.75, 10.75, 10.75, 11.25, 11.25, 10.75])
    d = decisoes_selic(s)
    assert [x["para"] for x in d] == [10.75, 11.25, 10.75]
    assert d[0] == {"data": "2025-01-08", "de": 11.25, "para": 10.75, "variacao_pp": -0.5}
    assert d[-1]["variacao_pp"] == 0.75


def test_decisoes_selic_respeita_limite_e_series_sem_mudanca():
    assert decisoes_selic(_selic([13.75] * 10)) == []
    assert decisoes_selic(_selic([13.75])) == []
    s = _selic([1.0, 2.0, 3.0, 4.0, 5.0])
    assert len(decisoes_selic(s, limite=2)) == 2


def test_decisoes_selic_ignora_ruido_de_ponto_flutuante():
    s = _selic([10.0, 10.0 + 1e-12, 10.0])
    assert decisoes_selic(s) == []


@pytest.mark.parametrize(
    ("valor", "situacao"),
    [(3.0, "dentro"), (1.5, "dentro"), (4.5, "dentro"), (4.51, "acima"), (1.49, "abaixo")],
)
def test_meta_inflacao_classifica_pela_banda(valor, situacao):
    s = pd.Series([valor], index=pd.to_datetime(["2026-09-01"]))
    r = situacao_meta_inflacao(s)
    assert r["situacao"] == situacao
    assert (r["piso"], r["meta"], r["teto"]) == (1.5, 3.0, 4.5)
    assert r["desvio_pp"] == pytest.approx(valor - 3.0, abs=1e-4)


def test_meta_inflacao_conta_meses_consecutivos_fora_da_banda():
    idx = pd.date_range("2026-01-01", periods=7, freq="MS")
    s = pd.Series([3.0, 5.0, 4.8, 4.9, 5.1, 5.2, 5.3], index=idx)
    r = situacao_meta_inflacao(s)
    assert r["meses_consecutivos_fora"] == 6
    assert r["meses_para_descumprimento"] == 6
    s2 = pd.Series([5.0, 5.0, 3.0], index=idx[:3])
    assert situacao_meta_inflacao(s2)["meses_consecutivos_fora"] == 0


def test_meta_inflacao_sem_dados():
    assert situacao_meta_inflacao(pd.Series(dtype=float)) is None
    assert situacao_meta_inflacao(pd.Series([float("nan")], index=pd.to_datetime(["2026-01-01"]))) is None


def test_consulta_destaques_monta_os_dois_blocos(monkeypatch, ipca_mensal):
    pytest.importorskip("sqlalchemy")
    from bcb_pipeline import consultas

    selic = pd.Series(
        [13.75] * 5 + [14.25] * 5,
        index=pd.date_range("2026-08-03", periods=10, freq="D"),
    )
    monkeypatch.setattr(consultas, "carregar_series", lambda engine: {"selic": selic, "ipca": ipca_mensal})
    r = consultas.destaques(engine=None)
    assert r["selic"]["atual"] == 14.25
    assert r["selic"]["decisoes"][0]["variacao_pp"] == 0.5
    assert r["selic"]["dias_desde_ultima_mudanca"] == 4
    assert r["meta_inflacao"]["situacao"] in {"dentro", "acima", "abaixo"}


def test_consulta_destaques_sem_dados(monkeypatch):
    pytest.importorskip("sqlalchemy")
    from bcb_pipeline import consultas

    monkeypatch.setattr(consultas, "carregar_series", lambda engine: {})
    assert consultas.destaques(engine=None) == {"selic": None, "meta_inflacao": None}
