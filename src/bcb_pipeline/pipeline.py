"""Orquestração da pipeline: extração -> transformação -> qualidade -> carga -> previsão.

Falhas são isoladas por série: um indicador fora do ar ou reprovado na
qualidade não impede a carga dos demais. A execução termina como ``sucesso``,
``parcial`` ou ``falha`` e tudo fica registrado em ``etl_execucoes``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import Engine

from . import carga
from .banco import aplicar_migracoes, obter_engine
from .config import SERIES, Serie, serie
from .extracao import ClienteSGS, data_inicio_incremental
from .previsao import prever_ipca
from .qualidade import check_reconciliacao_ipca, lote_aprovado, validar_lote
from .transformacao import transformar

log = logging.getLogger(__name__)


@dataclass
class ResumoExecucao:
    id_execucao: int
    status: str
    por_serie: dict[str, str] = field(default_factory=dict)
    linhas_extraidas: int = 0
    linhas_inseridas: int = 0
    linhas_revisadas: int = 0


def _processar_serie(engine: Engine, cliente: ClienteSGS, s: Serie, completo: bool, id_execucao: int) -> dict:
    inicio = time.perf_counter()
    registro = {
        "id_execucao": id_execucao,
        "codigo_bcb": s.codigo,
        "status": "falha",
        "desde": None,
        "linhas_extraidas": 0,
        "linhas_inseridas": 0,
        "linhas_revisadas": 0,
        "erro": None,
    }
    try:
        ultima = None if completo else carga.ultima_data(engine, s)
        desde = data_inicio_incremental(s, ultima)
        registro["desde"] = desde.date()
        log.info("[%s] %s — coletando desde %s", s.codigo, s.nome, desde.date())

        df = transformar(cliente.extrair(s, desde=desde), s)
        registro["linhas_extraidas"] = len(df)

        historico = carga.ler_serie(engine, s)
        combinado = pd.concat([historico[historico["data"] < desde], df[["data", "valor"]]], ignore_index=True)
        resultados = validar_lote(df, s, incremental=ultima is not None, historico=combinado)
        carga.registrar_qualidade(engine, id_execucao, resultados)

        if not lote_aprovado(resultados):
            registro["status"] = "quarentena"
            registro["erro"] = "; ".join(r.detalhe for r in resultados if r.status.value == "falha")
            log.error("[%s] lote reprovado na qualidade: %s", s.codigo, registro["erro"])
        else:
            r = carga.gravar_observacoes(engine, df.dropna(), id_execucao)
            registro.update(status="sucesso", linhas_inseridas=r.inseridas, linhas_revisadas=r.revisadas)
            log.info("[%s] %d novas, %d revisadas", s.codigo, r.inseridas, r.revisadas)
    except Exception as exc:  # isolamento por série
        registro["erro"] = f"{type(exc).__name__}: {exc}"[:2000]
        log.exception("[%s] falha na série", s.codigo)
    registro["duracao_ms"] = int((time.perf_counter() - inicio) * 1000)
    carga.registrar_serie(engine, **registro)
    return registro


def _reconciliar_ipca(engine: Engine, id_execucao: int) -> None:
    mensal, oficial = serie("ipca"), serie("ipca_12m")
    df_m, df_o = carga.ler_serie(engine, mensal), carga.ler_serie(engine, oficial)
    if df_m.empty or df_o.empty:
        return
    carga.registrar_qualidade(engine, id_execucao, [check_reconciliacao_ipca(df_m, df_o, oficial)])


def _atualizar_previsao(engine: Engine) -> None:
    s = serie("ipca")
    df = carga.ler_serie(engine, s)
    if df.empty:
        return
    hist = df.set_index("data")["valor"]
    resultado = prever_ipca(hist)
    carga.gravar_previsao(engine, s, resultado, hist.index.max().date())
    m = resultado.metricas.iloc[0]
    log.info(
        "Previsão IPCA: modelo %s (MAE %.3f p.p., skill %.0f%% vs. ingênuo sazonal)",
        resultado.modelo_escolhido,
        m["mae"],
        m["skill"] * 100,
    )


def executar(
    modo: str = "incremental",
    codigos: list[str] | None = None,
    gatilho: str = "manual",
    com_previsao: bool = True,
    engine: Engine | None = None,
    cliente: ClienteSGS | None = None,
) -> ResumoExecucao:
    engine = engine or obter_engine()
    cliente = cliente or ClienteSGS()
    selecionadas = tuple(serie(c) for c in codigos) if codigos else SERIES

    novas = aplicar_migracoes(engine)
    if novas:
        log.info("Migrações aplicadas: %s", ", ".join(novas))
    carga.sincronizar_indicadores(engine)

    id_execucao = carga.iniciar_execucao(engine, modo, gatilho)
    resumo = ResumoExecucao(id_execucao=id_execucao, status="executando")
    log.info("Execução #%d iniciada (%s, %d séries)", id_execucao, modo, len(selecionadas))

    erro_geral = None
    try:
        for s in selecionadas:
            reg = _processar_serie(engine, cliente, s, modo == "completo", id_execucao)
            resumo.por_serie[s.codigo] = reg["status"]
            resumo.linhas_extraidas += reg["linhas_extraidas"]
            resumo.linhas_inseridas += reg["linhas_inseridas"]
            resumo.linhas_revisadas += reg["linhas_revisadas"]

        _reconciliar_ipca(engine, id_execucao)
        if com_previsao and resumo.por_serie.get("433") == "sucesso":
            try:
                _atualizar_previsao(engine)
            except Exception:
                log.exception("Falha ao gerar previsão (dados carregados normalmente)")
    except Exception as exc:
        erro_geral = f"{type(exc).__name__}: {exc}"
        log.exception("Execução abortada")

    sucessos = sum(1 for v in resumo.por_serie.values() if v == "sucesso")
    if erro_geral or sucessos == 0:
        resumo.status = "falha"
    elif sucessos == len(selecionadas):
        resumo.status = "sucesso"
    else:
        resumo.status = "parcial"

    falhas = [f"{c}: {v}" for c, v in resumo.por_serie.items() if v != "sucesso"]
    carga.finalizar_execucao(
        engine,
        id_execucao,
        status=resumo.status,
        linhas_extraidas=resumo.linhas_extraidas,
        linhas_inseridas=resumo.linhas_inseridas,
        linhas_revisadas=resumo.linhas_revisadas,
        requisicoes_http=cliente.estatisticas.requisicoes,
        erro=erro_geral or ("; ".join(falhas) or None),
    )
    log.info(
        "Execução #%d: %s — %d extraídas, %d novas, %d revisadas",
        id_execucao,
        resumo.status,
        resumo.linhas_extraidas,
        resumo.linhas_inseridas,
        resumo.linhas_revisadas,
    )
    return resumo
