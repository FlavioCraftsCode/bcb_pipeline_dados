"""API REST do Data Warehouse + servidor do painel.

Rodar localmente::

    uvicorn bcb_api.main:app --reload --app-dir src

Documentação interativa (OpenAPI) em ``/docs``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bcb_pipeline import __version__, consultas
from bcb_pipeline.banco import obter_engine
from bcb_pipeline.config import SERIES_POR_SLUG

from . import schemas

app = FastAPI(
    title="BCB Data Warehouse API",
    version=__version__,
    description=(
        "Indicadores macroeconômicos do Banco Central do Brasil (SGS), com camada analítica, "
        "resultados de qualidade de dados, histórico de execuções da pipeline e previsão do IPCA."
    ),
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def cabecalhos_de_cache(request: Request, call_next):
    """Respostas de leitura podem ser reaproveitadas por navegadores e CDNs por 1 minuto.

    ``/api/saude`` fica de fora: é o que um monitor consulta para saber o estado real.
    """
    resposta = await call_next(request)
    caminho = request.url.path
    if request.method == "GET" and caminho.startswith("/api/") and resposta.status_code == 200:
        if caminho == "/api/saude":
            resposta.headers["Cache-Control"] = "no-store"
        else:
            resposta.headers.setdefault("Cache-Control", "public, max-age=60, stale-while-revalidate=300")
    return resposta


def _engine():
    return obter_engine()


@app.get("/api/saude", tags=["operação"], summary="Verifica banco e última execução", response_model=schemas.Saude)
def saude():
    return consultas.saude(_engine())


@app.get("/api/indicadores", tags=["dados"], summary="Catálogo com último valor e minigráfico")
def indicadores():
    return consultas.indicadores(_engine())


@app.get("/api/series/{slug}", tags=["dados"], summary="Série histórica de um indicador")
def serie(
    slug: str,
    frequencia: Literal["mensal", "diaria"] = "mensal",
    desde: date | None = Query(None, description="Data inicial ISO (aaaa-mm-dd)"),
):
    if slug not in SERIES_POR_SLUG:
        raise HTTPException(404, f"Indicador '{slug}' não existe. Opções: {', '.join(SERIES_POR_SLUG)}")
    return consultas.serie_historica(_engine(), slug, frequencia, desde.isoformat() if desde else None)


@app.get("/api/painel", tags=["análise"], summary="Painel mensal com métricas derivadas")
def painel(desde: date = date(2000, 1, 1)):
    return consultas.painel(_engine(), desde.isoformat())


@app.get("/api/correlacoes", tags=["análise"], summary="Correlação de Spearman entre indicadores")
def correlacoes(desde: date = date(2012, 1, 1)):
    return consultas.correlacoes(_engine(), desde.isoformat())


@app.get(
    "/api/destaques",
    tags=["análise"],
    summary="Decisões recentes da Selic e situação do IPCA frente à meta de inflação",
    response_model=schemas.Destaques,
)
def destaques(limite: int = Query(8, ge=1, le=50, description="Quantas mudanças da Selic devolver")):
    return consultas.destaques(_engine(), limite)


@app.get("/api/previsao", tags=["análise"], summary="Previsão do IPCA e métricas do backtest")
def previsao():
    return consultas.previsao(_engine())


@app.get(
    "/api/qualidade",
    tags=["operação"],
    summary="Resultados de qualidade da última execução",
    response_model=schemas.Qualidade,
)
def qualidade():
    return consultas.qualidade(_engine())


@app.get(
    "/api/execucoes",
    tags=["operação"],
    summary="Histórico de execuções da pipeline",
    response_model=schemas.Execucoes,
)
def execucoes(limite: int = Query(20, ge=1, le=200)):
    return consultas.execucoes(_engine(), limite)


# ------------------------------------------------------------- front-end
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str):
        if caminho.startswith("api/"):
            raise HTTPException(404, "Rota não encontrada")
        arquivo = (DIST / caminho).resolve()
        if caminho and arquivo.is_file() and arquivo.is_relative_to(DIST):
            return FileResponse(arquivo)
        return FileResponse(DIST / "index.html")
