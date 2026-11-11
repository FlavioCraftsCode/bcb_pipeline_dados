"""Testes de integração contra um PostgreSQL real.

Rodam no CI (serviço ``postgres`` do GitHub Actions) ou localmente com::

    docker compose up -d postgres_dw
    DATABASE_URL_TESTE=postgresql+psycopg2://admin:securepassword@localhost:5432/bcb_test pytest -m integracao

A API do BCB é substituída por uma sessão falsa que serve dados sintéticos,
então os testes são determinísticos e não dependem de rede.
"""

from __future__ import annotations

import os
import re
from datetime import date

import numpy as np
import pandas as pd
import pytest

from conftest import RespostaFalsa, _ipca_sintetico

pytestmark = pytest.mark.integracao

# Variável própria: o teste recria o schema, então nunca usa o DATABASE_URL "de verdade".
DATABASE_URL = os.getenv("DATABASE_URL_TESTE")
sqlalchemy = pytest.importorskip("sqlalchemy")
if not DATABASE_URL:
    pytest.skip("DATABASE_URL_TESTE não definido", allow_module_level=True)

from sqlalchemy import create_engine, text  # noqa: E402

from bcb_pipeline import consultas  # noqa: E402
from bcb_pipeline.analise import acumulado_12m  # noqa: E402
from bcb_pipeline.config import Configuracoes  # noqa: E402
from bcb_pipeline.extracao import ClienteSGS  # noqa: E402
from bcb_pipeline.pipeline import executar  # noqa: E402

HOJE = pd.Timestamp(date.today())


def _universo() -> dict[str, pd.Series]:
    """Dados sintéticos por código SGS, terminando perto de hoje."""
    fim_mensal = (HOJE - pd.DateOffset(months=1)).replace(day=1)
    ipca = _ipca_sintetico("1995-01-01", fim_mensal.strftime("%Y-%m-%d"))
    dias = pd.bdate_range("2015-01-02", HOJE - pd.Timedelta(days=1))
    rng = np.random.default_rng(1)
    meses = pd.date_range("2012-03-01", fim_mensal, freq="MS")
    return {
        "433": ipca,
        "13522": acumulado_12m(ipca).round(2).dropna(),
        "189": ipca * 1.1,
        "432": pd.Series(np.where(dias < "2021-03-17", 2.0, 13.75), index=dias),
        "1": pd.Series(5 + rng.normal(0, 0.02, len(dias)).cumsum(), index=dias).round(4),
        "24364": pd.Series(140 + rng.normal(0, 0.5, len(meses)).cumsum(), index=meses[: len(meses)]).round(2),
        "24369": pd.Series(np.linspace(12, 6, len(meses)), index=meses).round(1),
    }


class SessaoSGS:
    """Responde como o SGS: filtra o universo pela janela pedida."""

    def __init__(self, universo: dict[str, pd.Series]) -> None:
        self.universo = universo
        self.headers: dict = {}
        self.chamadas = 0

    def get(self, url, params=None, timeout=None):
        self.chamadas += 1
        codigo = re.search(r"sgs\.(\d+)/", url).group(1)
        ini = pd.to_datetime(params["dataInicial"], format="%d/%m/%Y")
        fim = pd.to_datetime(params["dataFinal"], format="%d/%m/%Y")
        s = self.universo[codigo]
        s = s[(s.index >= ini) & (s.index <= fim)]
        if s.empty:
            return RespostaFalsa(404)
        return RespostaFalsa(200, [{"data": d.strftime("%d/%m/%Y"), "valor": f"{v}"} for d, v in s.items()])


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    consultas.CACHE.ttl = 0
    yield eng
    eng.dispose()


def _cliente(universo):
    return ClienteSGS(Configuracoes(tentativas=1), sessao=SessaoSGS(universo), dormir=lambda _: None)


def test_carga_completa_incremental_e_revisao(engine):
    universo = _universo()

    r1 = executar("completo", gatilho="teste", engine=engine, cliente=_cliente(universo))
    assert r1.status == "sucesso", r1.por_serie
    total = sum(len(s) for s in universo.values())
    assert r1.linhas_inseridas == total

    # Reexecução incremental sem novidades: idempotente
    r2 = executar("incremental", gatilho="teste", engine=engine, cliente=_cliente(universo), com_previsao=False)
    assert r2.status == "sucesso" and r2.linhas_inseridas == 0 and r2.linhas_revisadas == 0

    # A fonte revisa o IBC-Br dentro da janela de revisão -> capturado como revisão
    revisado = dict(universo)
    ibc = universo["24364"].copy()
    ibc.iloc[-2] += 1.0
    revisado["24364"] = ibc
    r3 = executar("incremental", ["24364"], gatilho="teste", engine=engine, cliente=_cliente(revisado))
    assert r3.linhas_revisadas == 1 and r3.linhas_inseridas == 0

    with engine.connect() as conn:
        dup = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT 1 FROM fato_indicadores"
                " GROUP BY id_indicador, id_tempo HAVING count(*) > 1) d"
            )
        ).scalar()
        assert dup == 0
        status = conn.execute(text("SELECT status FROM etl_execucoes ORDER BY id_execucao")).scalars().all()
        assert status == ["sucesso", "sucesso", "sucesso"]
        rec = conn.execute(
            text(
                "SELECT status FROM dq_resultados WHERE checagem = 'reconciliacao_ipca_12m'"
                " ORDER BY id_resultado LIMIT 1"
            )
        ).scalar()
        assert rec == "ok"


def test_lote_bloqueado_vai_para_quarentena(engine):
    universo = _universo()
    ruim = dict(universo)
    selic = universo["432"].copy()
    selic.iloc[-1] = 999.0  # fora da faixa válida
    ruim["432"] = selic
    antes = consultas.serie_historica(engine, "selic", "diaria")["pontos"][-1]["valor"]
    r = executar("incremental", ["432"], gatilho="teste", engine=engine, cliente=_cliente(ruim), com_previsao=False)
    # Isolar o lote é o sistema funcionando: a execução conclui com isolamento.
    assert r.status == "concluido_com_isolamento" and r.por_serie["432"] == "quarentena"
    consultas.CACHE._series = {}
    assert consultas.serie_historica(engine, "selic", "diaria")["pontos"][-1]["valor"] == antes


def test_consultas_servem_o_painel(engine):
    consultas.CACHE._series = {}
    ind = consultas.indicadores(engine)
    assert {i["slug"] for i in ind} >= {"selic", "ipca", "dolar", "ibcbr"}
    painel = consultas.painel(engine)
    assert painel["ultimo"]["juro_real"]["valor"] is not None
    prev = consultas.previsao(engine)
    assert prev["disponivel"] and len(prev["previsao"]) == 12
    assert consultas.qualidade(engine)["resultados"]
    assert consultas.execucoes(engine)["execucoes"][0]["status"] == "concluido_com_isolamento"
    q = consultas.qualidade(engine)
    assert {r["status"] for r in q["resultados"]} <= {"ok", "informativo", "bloqueante"}
    assert any(r["status"] == "bloqueante" and r["checagem"] == "faixa_valida" for r in q["resultados"])
    assert len(consultas.correlacoes(engine)["matriz"]) >= 4


def test_api(engine, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import bcb_api.main as api

    monkeypatch.setattr(api, "_engine", lambda: engine)
    cliente = TestClient(api.app)
    assert cliente.get("/api/saude").json()["banco"] == "ok"
    assert cliente.get("/api/series/ipca").status_code == 200
    assert cliente.get("/api/series/nao-existe").status_code == 404
    assert cliente.get("/api/previsao").json()["disponivel"] is True
    ex = cliente.get("/api/execucoes").json()
    assert ex["execucoes"][0]["status"] == "concluido_com_isolamento"
    assert cliente.get("/api/qualidade").status_code == 200
    assert cliente.get("/openapi.json").status_code == 200
