"""Orquestração da pipeline: extração -> transformação -> qualidade -> carga -> previsão.

Circuito de Proteção de Dados: cada série é processada de forma isolada. Um
lote reprovado por uma checagem bloqueante vai para quarentena e uma fonte
indisponível interrompe apenas aquela série; as demais seguem para o Data
Warehouse. A execução termina como ``sucesso``, ``concluido_com_isolamento``
ou ``interrompida`` (ver :mod:`bcb_pipeline.status`) e tudo fica registrado em
``etl_execucoes``.
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
from .status import StatusCheck, StatusExecucao, StatusSerie, status_da_execucao
from .transformacao import transformar

log = logging.getLogger(__name__)


@dataclass
class ResumoExecucao:
    id_execucao: int
    status: StatusExecucao
    por_serie: dict[str, StatusSerie] = field(default_factory=dict)
    linhas_extraidas: int = 0
    linhas_inseridas: int = 0
    linhas_revisadas: int = 0


def _processar_serie(engine: Engine, cliente: ClienteSGS, s: Serie, completo: bool, id_execucao: int) -> dict:
    inicio = time.perf_counter()
    registro = {
        "id_execucao": id_execucao,
        "codigo_bcb": s.codigo,
        "status": StatusSerie.INTERROMPIDA,
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
            registro["status"] = StatusSerie.QUARENTENA
            registro["erro"] = "; ".join(r.detalhe for r in resultados if r.status is StatusCheck.BLOQUEANTE)
            log.warning("[%s] lote isolado em quarentena (checagem bloqueante): %s", s.codigo, registro["erro"])
        else:
            r = carga.gravar_observacoes(engine, df.dropna(), id_execucao)
            registro.update(status=StatusSerie.SUCESSO, linhas_inseridas=r.inseridas, linhas_revisadas=r.revisadas)
            log.info("[%s] %d novas, %d revisadas", s.codigo, r.inseridas, r.revisadas)
    except Exception as exc:  # isolamento por série
        registro["erro"] = f"{type(exc).__name__}: {exc}"[:2000]
        log.exception("[%s] série interrompida", s.codigo)
    registro["duracao_ms"] = int((time.perf_counter() - inicio) * 1000)
    carga.registrar_serie(engine, **{**registro, "status": registro["status"].value})
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
    resumo = ResumoExecucao(id_execucao=id_execucao, status=StatusExecucao.EXECUTANDO)
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
        if com_previsao and resumo.por_serie.get("433") is StatusSerie.SUCESSO:
            try:
                _atualizar_previsao(engine)
            except Exception:
                log.exception("Previsão não atualizada (dados carregados normalmente)")
    except Exception as exc:
        erro_geral = f"{type(exc).__name__}: {exc}"
        log.exception("Execução interrompida")

    resumo.status = status_da_execucao(resumo.por_serie, erro_geral)
    isoladas = [f"{c}: {v.value}" for c, v in resumo.por_serie.items() if v is not StatusSerie.SUCESSO]
    carga.finalizar_execucao(
        engine,
        id_execucao,
        status=resumo.status.value,
        linhas_extraidas=resumo.linhas_extraidas,
        linhas_inseridas=resumo.linhas_inseridas,
        linhas_revisadas=resumo.linhas_revisadas,
        requisicoes_http=cliente.estatisticas.requisicoes,
        erro=erro_geral or ("; ".join(isoladas) or None),
    )
    log.info(
        "Execução #%d: %s — %d extraídas, %d novas, %d revisadas",
        id_execucao,
        resumo.status.value,
        resumo.linhas_extraidas,
        resumo.linhas_inseridas,
        resumo.linhas_revisadas,
    )
    return resumo
