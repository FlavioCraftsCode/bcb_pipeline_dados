"""Contratos de resposta das rotas operacionais (documentados no OpenAPI em ``/docs``).

Os status são enums da :mod:`bcb_pipeline.status`, então qualquer valor fora do
vocabulário de governança é rejeitado na serialização e aparece explicitamente
na documentação da API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bcb_pipeline.status import StatusCheck, StatusExecucao, StatusSerie


class ResultadoQualidade(BaseModel):
    codigo_bcb: str
    slug: str | None = None
    nome_indicador: str | None = None
    checagem: str = Field(description="Nome da regra de qualidade, ex.: faixa_valida")
    status: StatusCheck = Field(description="ok, informativo (observabilidade) ou bloqueante (lote isolado)")
    detalhe: str
    valor_observado: float | None = None
    verificado_em: str | None = None


class Frescor(BaseModel):
    codigo_bcb: str
    slug: str | None = None
    nome_indicador: str
    periodicidade: str | None = None
    ultima_data: str | None = None
    observacoes: int
    ultima_atualizacao: str | None = None
    dias_desde_ultima: int | None = None


class ResumoQualidadeExecucao(BaseModel):
    id_execucao: int
    ok: int
    informativo: int
    bloqueante: int


class Qualidade(BaseModel):
    id_execucao: int | None
    resultados: list[ResultadoQualidade]
    frescor: list[Frescor]
    historico: list[ResumoQualidadeExecucao] = []


class Execucao(BaseModel):
    id_execucao: int
    iniciado_em: str
    finalizado_em: str | None = None
    status: StatusExecucao = Field(
        description="executando, sucesso, concluido_com_isolamento (séries isoladas pelo "
        "Circuito de Proteção de Dados) ou interrompida (incidente operacional)"
    )
    modo: str
    gatilho: str
    linhas_extraidas: int
    linhas_inseridas: int
    linhas_revisadas: int
    requisicoes_http: int
    erro: str | None = Field(None, description="Resumo das séries isoladas ou do incidente")
    duracao_s: float | None = None


class ExecucaoSerie(BaseModel):
    id_execucao: int
    codigo_bcb: str
    slug: str | None = None
    status: StatusSerie = Field(description="sucesso, quarentena ou interrompida")
    desde: str | None = None
    linhas_extraidas: int
    linhas_inseridas: int
    linhas_revisadas: int
    duracao_ms: int
    erro: str | None = None


class Execucoes(BaseModel):
    execucoes: list[Execucao]
    ultima_por_serie: list[ExecucaoSerie]


class UltimaExecucao(BaseModel):
    id: int
    status: StatusExecucao
    finalizado_em: str | None = None


class Saude(BaseModel):
    status: str
    banco: str
    ultima_execucao: UltimaExecucao | None = None


class DecisaoSelic(BaseModel):
    data: str = Field(description="Início da vigência da nova meta (aaaa-mm-dd)")
    de: float
    para: float
    variacao_pp: float


class DestaqueSelic(BaseModel):
    data: str
    atual: float | None
    dias_desde_ultima_mudanca: int
    decisoes: list[DecisaoSelic]


class MetaInflacao(BaseModel):
    data: str
    ipca_12m: float
    meta: float
    piso: float
    teto: float
    desvio_pp: float
    situacao: Literal["dentro", "acima", "abaixo"]
    meses_consecutivos_fora: int
    meses_para_descumprimento: int


class Destaques(BaseModel):
    selic: DestaqueSelic | None = None
    meta_inflacao: MetaInflacao | None = None
