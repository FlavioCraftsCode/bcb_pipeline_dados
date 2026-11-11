"""Vocabulário de status da plataforma — fonte única de verdade.

Três níveis, do mais fino ao mais amplo:

``StatusCheck`` — resultado de uma checagem de qualidade em um lote
    * ``ok``           — checagem aprovada.
    * ``informativo``  — anomalia registrada para observabilidade; o lote segue
                         para o Data Warehouse (ex.: outlier estatístico, atraso
                         de divulgação da fonte).
    * ``bloqueante``   — o lote viola uma regra de integridade e é barrado na
                         origem; o Circuito de Proteção de Dados o isola em
                         quarentena e o histórico já carregado é preservado.

``StatusSerie`` — desfecho de uma série dentro de uma execução
    * ``sucesso``      — lote aprovado e carregado.
    * ``quarentena``   — lote isolado por uma checagem bloqueante.
    * ``interrompida`` — a série não pôde ser processada (fonte indisponível
                         após as novas tentativas, ou erro inesperado).

``StatusExecucao`` — desfecho da execução como um todo
    * ``executando``                — em andamento.
    * ``sucesso``                   — todas as séries carregadas.
    * ``concluido_com_isolamento``  — a execução terminou normalmente e isolou
                                      ao menos uma série (quarentena ou fonte
                                      indisponível); as demais foram carregadas.
    * ``interrompida``              — a execução não chegou ao fim (erro de
                                      infraestrutura) ou nenhuma série pôde ser
                                      processada.

``interrompida`` é deliberadamente distinto de ``concluido_com_isolamento``:
isolar um lote ruim é o sistema funcionando; não conseguir processar é um
incidente operacional e precisa continuar visível como tal.
"""

from __future__ import annotations

from enum import Enum


class StatusCheck(str, Enum):
    OK = "ok"
    INFORMATIVO = "informativo"
    BLOQUEANTE = "bloqueante"


class StatusSerie(str, Enum):
    SUCESSO = "sucesso"
    QUARENTENA = "quarentena"
    INTERROMPIDA = "interrompida"


class StatusExecucao(str, Enum):
    EXECUTANDO = "executando"
    SUCESSO = "sucesso"
    CONCLUIDO_COM_ISOLAMENTO = "concluido_com_isolamento"
    INTERROMPIDA = "interrompida"


def status_da_execucao(por_serie: dict[str, StatusSerie], erro_geral: str | None) -> StatusExecucao:
    """Consolida o desfecho das séries no status da execução."""
    if erro_geral or not por_serie:
        return StatusExecucao.INTERROMPIDA
    valores = set(por_serie.values())
    if valores == {StatusSerie.SUCESSO}:
        return StatusExecucao.SUCESSO
    if valores == {StatusSerie.INTERROMPIDA}:
        return StatusExecucao.INTERROMPIDA
    return StatusExecucao.CONCLUIDO_COM_ISOLAMENTO
