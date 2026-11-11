"""Exporta um snapshot JSON do DW para o painel rodar como site estático.

É o que alimenta a demo pública no GitHub Pages: o workflow agendado roda a
pipeline num Postgres efêmero, chama esta exportação e publica o front-end.
Os arquivos espelham as rotas da API (``/api/x`` -> ``data/x.json``).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine

from . import consultas
from .config import SERIES, Periodicidade

log = logging.getLogger(__name__)


def _salvar(destino: Path, nome: str, conteudo) -> None:
    caminho = destino / f"{nome}.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def exportar(engine: Engine, destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    arquivos = {
        "indicadores": consultas.indicadores(engine),
        "painel": consultas.painel(engine),
        "correlacoes": consultas.correlacoes(engine),
        "previsao": consultas.previsao(engine),
        "qualidade": consultas.qualidade(engine),
        "execucoes": consultas.execucoes(engine),
        "saude": consultas.saude(engine),
    }
    for s in SERIES:
        arquivos[f"series/{s.slug}-mensal"] = consultas.serie_historica(engine, s.slug, "mensal")
        if s.periodicidade is Periodicidade.DIARIA:
            arquivos[f"series/{s.slug}-diaria"] = consultas.serie_historica(engine, s.slug, "diaria")
    arquivos["meta"] = {"gerado_em": datetime.now().astimezone().isoformat(), "modo": "estatico"}
    for nome, conteudo in arquivos.items():
        _salvar(destino, nome, conteudo)
    log.info("Snapshot exportado: %d arquivos em %s", len(arquivos), destino)
    return sorted(arquivos)
