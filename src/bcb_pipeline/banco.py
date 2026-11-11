"""Conexão com o Data Warehouse e executor de migrações versionadas."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, text

from .config import CONFIG

log = logging.getLogger(__name__)

DIR_MIGRACOES = Path(__file__).resolve().parents[2] / "database" / "migrations"


@lru_cache(maxsize=4)
def obter_engine(url: str | None = None) -> Engine:
    return create_engine(url or CONFIG.database_url, pool_pre_ping=True, future=True)


def aplicar_migracoes(engine: Engine, diretorio: Path = DIR_MIGRACOES) -> list[str]:
    """Aplica, em ordem, as migrações ``NNN_*.sql`` ainda não registradas.

    Cada arquivo roda numa transação própria: ou entra inteiro, ou não entra.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migracoes ("
                " versao VARCHAR(80) PRIMARY KEY,"
                " aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
        aplicadas = set(conn.execute(text("SELECT versao FROM schema_migracoes")).scalars())

    novas = []
    for arquivo in sorted(diretorio.glob("[0-9][0-9][0-9]_*.sql")):
        if arquivo.name in aplicadas:
            continue
        log.info("Aplicando migração %s", arquivo.name)
        bruto = engine.raw_connection()
        try:
            with bruto.cursor() as cur:
                # Cursor DBAPI sem parâmetros: executa o script inteiro, sem
                # interpretar ':' ou '%' como marcadores.
                cur.execute(arquivo.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migracoes (versao) VALUES (%s)", (arquivo.name,))
            bruto.commit()
        except Exception:
            bruto.rollback()
            raise
        finally:
            bruto.close()
        novas.append(arquivo.name)
    return novas
