"""Contrato HTTP da API sem banco: as consultas são substituídas por dublês."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from bcb_api import main  # noqa: E402


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(main, "_engine", lambda: object())
    return TestClient(main.app)


def test_data_invalida_vira_422_e_nao_500(cliente):
    assert cliente.get("/api/series/selic?desde=ontem").status_code == 422
    assert cliente.get("/api/painel?desde=2020-13-45").status_code == 422
    assert cliente.get("/api/correlacoes?desde=abc").status_code == 422


def test_data_valida_chega_a_consulta_como_iso(cliente, monkeypatch):
    visto = {}

    def falso(engine, slug, frequencia, desde):
        visto.update(slug=slug, frequencia=frequencia, desde=desde)
        return {"pontos": []}

    monkeypatch.setattr(main.consultas, "serie_historica", falso)
    r = cliente.get("/api/series/selic?desde=2020-05-01&frequencia=diaria")
    assert r.status_code == 200
    assert visto == {"slug": "selic", "frequencia": "diaria", "desde": "2020-05-01"}


def test_slug_inexistente_continua_404(cliente):
    assert cliente.get("/api/series/nao-existe").status_code == 404


def test_cache_control_em_leituras_e_no_store_na_saude(cliente, monkeypatch):
    monkeypatch.setattr(main.consultas, "painel", lambda engine, desde: {"ok": True})
    monkeypatch.setattr(
        main.consultas, "saude", lambda engine: {"status": "ok", "banco": "ok", "ultima_execucao": None}
    )
    assert "max-age=60" in cliente.get("/api/painel").headers["cache-control"]
    assert cliente.get("/api/saude").headers["cache-control"] == "no-store"


def test_destaques_valida_limite_e_contrato(cliente, monkeypatch):
    corpo = {
        "selic": {
            "data": "2026-09-30",
            "atual": 14.25,
            "dias_desde_ultima_mudanca": 12,
            "decisoes": [{"data": "2026-09-18", "de": 13.75, "para": 14.25, "variacao_pp": 0.5}],
        },
        "meta_inflacao": None,
    }
    monkeypatch.setattr(main.consultas, "destaques", lambda engine, limite: corpo)
    assert cliente.get("/api/destaques").json()["selic"]["decisoes"][0]["para"] == 14.25
    assert cliente.get("/api/destaques?limite=0").status_code == 422
