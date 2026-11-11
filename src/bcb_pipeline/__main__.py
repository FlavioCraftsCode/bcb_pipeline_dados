"""Interface de linha de comando.

Exemplos::

    python -m bcb_pipeline executar                 # carga incremental de todas as séries
    python -m bcb_pipeline executar --completo      # recarga completa (idempotente)
    python -m bcb_pipeline executar --series 432 433
    python -m bcb_pipeline migrar
    python -m bcb_pipeline prever
    python -m bcb_pipeline exportar --destino frontend/public/data
    python -m bcb_pipeline series                   # lista o catálogo
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import CONFIG, SERIES


def _configurar_log() -> None:
    logging.basicConfig(
        level=CONFIG.log_nivel,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bcb_pipeline", description="Pipeline de dados do Banco Central (SGS)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_exec = sub.add_parser("executar", help="Roda a pipeline ETL")
    p_exec.add_argument("--completo", action="store_true", help="Recoleta todo o histórico")
    p_exec.add_argument("--series", nargs="+", metavar="CODIGO", help="Códigos SGS ou slugs")
    p_exec.add_argument("--sem-previsao", action="store_true", help="Não recalcula a previsão do IPCA")
    p_exec.add_argument("--gatilho", default="manual", help="Origem da execução (manual, agendado, ci)")

    sub.add_parser("migrar", help="Aplica migrações pendentes")
    sub.add_parser("prever", help="Recalcula a previsão do IPCA com os dados do DW")
    p_exp = sub.add_parser("exportar", help="Exporta snapshot JSON para o painel estático")
    p_exp.add_argument("--destino", type=Path, default=Path("frontend/public/data"))
    sub.add_parser("series", help="Lista as séries do catálogo")

    args = parser.parse_args(argv)
    _configurar_log()

    if args.comando == "series":
        for s in SERIES:
            print(f"{s.codigo:>6}  {s.slug:<11} {s.periodicidade.value:<7} {s.nome} [{s.unidade}]")
        return 0

    from .banco import aplicar_migracoes, obter_engine

    engine = obter_engine()
    if args.comando == "migrar":
        novas = aplicar_migracoes(engine)
        print("Nenhuma migração pendente." if not novas else "Aplicadas: " + ", ".join(novas))
        return 0
    if args.comando == "executar":
        from .pipeline import executar
        from .status import StatusExecucao

        resumo = executar(
            modo="completo" if args.completo else "incremental",
            codigos=args.series,
            gatilho=args.gatilho,
            com_previsao=not args.sem_previsao,
            engine=engine,
        )
        # Isolar lotes é comportamento esperado; só uma execução interrompida sai com erro.
        return 1 if resumo.status is StatusExecucao.INTERROMPIDA else 0
    if args.comando == "prever":
        from .pipeline import _atualizar_previsao

        _atualizar_previsao(engine)
        return 0
    if args.comando == "exportar":
        from .exportacao import exportar

        exportar(engine, args.destino)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
