from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _ipca_sintetico(inicio: str = "2000-01-01", fim: str = "2026-09-01", seed: int = 7) -> pd.Series:
    """IPCA mensal plausível: AR(1) + sazonalidade + ruído."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(inicio, fim, freq="MS")
    perfil = [0.25, 0.2, 0.05, 0.0, -0.05, -0.15, -0.1, -0.12, -0.05, 0.05, 0.05, 0.2]
    sazonal = dict(enumerate(perfil, start=1))
    v, nivel = [], 0.45
    for dt in idx:
        nivel = 0.4 + 0.85 * (nivel - 0.4) + rng.normal(0, 0.08)
        v.append(round(nivel + sazonal[dt.month] + rng.normal(0, 0.06), 2))
    return pd.Series(v, index=idx, name="valor")


@pytest.fixture
def ipca_mensal() -> pd.Series:
    return _ipca_sintetico()


class RespostaFalsa:
    def __init__(self, status: int, payload=None, texto: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = texto

    def json(self):
        return self._payload


class SessaoFalsa:
    """Imita ``requests.Session``: devolve respostas de uma fila e registra chamadas."""

    def __init__(self, respostas) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None):
        self.chamadas.append({"url": url, "params": params})
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def sessao_falsa():
    return SessaoFalsa
