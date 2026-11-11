"""Configuração central: catálogo de séries e parâmetros de execução.

O catálogo é a única fonte de verdade sobre *o que* a pipeline coleta. Adicionar
um indicador novo é uma linha aqui — extração, qualidade, carga, API e painel
passam a tratá-lo automaticamente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class Periodicidade(str, Enum):
    DIARIA = "diaria"
    MENSAL = "mensal"


@dataclass(frozen=True)
class Serie:
    codigo: str
    slug: str
    nome: str
    unidade: str
    periodicidade: Periodicidade
    fonte: str
    descricao: str
    inicio: str  # dd/mm/aaaa — primeira data com dados no SGS
    # Faixa plausível de valores: fora dela é erro de qualidade (dado corrompido).
    faixa_valida: tuple[float, float]
    # Atraso máximo aceitável entre hoje e a última observação (em dias).
    atraso_maximo_dias: int
    # Quantos períodos recentes são recoletados em toda carga incremental para
    # capturar revisões (o IBC-Br, por exemplo, é revisado meses depois).
    periodos_revisao: int = 3
    casas_decimais: int = 2
    tags: tuple[str, ...] = field(default_factory=tuple)


SERIES: tuple[Serie, ...] = (
    Serie(
        codigo="432",
        slug="selic",
        nome="Meta Selic",
        unidade="% a.a.",
        periodicidade=Periodicidade.DIARIA,
        fonte="Copom / BCB",
        descricao="Meta para a taxa Selic definida pelo Comitê de Política Monetária.",
        inicio="05/03/1999",
        faixa_valida=(0.0, 50.0),
        atraso_maximo_dias=7,
        periodos_revisao=10,
        tags=("juros", "destaque"),
    ),
    Serie(
        codigo="433",
        slug="ipca",
        nome="IPCA — variação mensal",
        unidade="%",
        periodicidade=Periodicidade.MENSAL,
        fonte="IBGE",
        descricao="Índice Nacional de Preços ao Consumidor Amplo, variação no mês.",
        inicio="01/01/1980",
        faixa_valida=(-5.0, 90.0),  # inclui a hiperinflação dos anos 80/90
        atraso_maximo_dias=75,
        tags=("inflacao", "destaque"),
    ),
    Serie(
        codigo="13522",
        slug="ipca_12m",
        nome="IPCA — acumulado em 12 meses (oficial)",
        unidade="%",
        periodicidade=Periodicidade.MENSAL,
        fonte="IBGE",
        descricao="Usada para reconciliar o acumulado que a própria pipeline calcula.",
        inicio="01/01/1980",
        faixa_valida=(-10.0, 7000.0),
        atraso_maximo_dias=75,
        tags=("inflacao", "referencia"),
    ),
    Serie(
        codigo="189",
        slug="igpm",
        nome="IGP-M — variação mensal",
        unidade="%",
        periodicidade=Periodicidade.MENSAL,
        fonte="FGV",
        descricao="Índice Geral de Preços do Mercado, variação no mês.",
        inicio="01/06/1989",
        faixa_valida=(-10.0, 90.0),
        atraso_maximo_dias=75,
        tags=("inflacao",),
    ),
    Serie(
        codigo="1",
        slug="dolar",
        nome="Dólar (PTAX venda)",
        unidade="R$/US$",
        periodicidade=Periodicidade.DIARIA,
        fonte="BCB",
        descricao="Taxa de câmbio livre, dólar americano, venda.",
        inicio="28/11/1984",
        faixa_valida=(0.0, 50.0),
        atraso_maximo_dias=7,
        periodos_revisao=10,
        casas_decimais=4,
        tags=("cambio", "destaque"),
    ),
    Serie(
        codigo="24364",
        slug="ibcbr",
        nome="IBC-Br (dessazonalizado)",
        unidade="índice",
        periodicidade=Periodicidade.MENSAL,
        fonte="BCB",
        descricao="Índice de Atividade Econômica do Banco Central, com ajuste sazonal.",
        inicio="01/01/2003",
        faixa_valida=(50.0, 300.0),
        atraso_maximo_dias=110,
        periodos_revisao=24,  # séries dessazonalizadas são revisadas para trás
        tags=("atividade", "destaque"),
    ),
    Serie(
        codigo="24369",
        slug="desemprego",
        nome="Taxa de desocupação (PNAD Contínua)",
        unidade="%",
        periodicidade=Periodicidade.MENSAL,
        fonte="IBGE",
        descricao="Taxa de desocupação, trimestre móvel.",
        inicio="01/03/2012",
        faixa_valida=(0.0, 30.0),
        atraso_maximo_dias=90,
        casas_decimais=1,
        tags=("trabalho",),
    ),
)

SERIES_POR_CODIGO: dict[str, Serie] = {s.codigo: s for s in SERIES}
SERIES_POR_SLUG: dict[str, Serie] = {s.slug: s for s in SERIES}


def serie(codigo_ou_slug: str) -> Serie:
    """Busca uma série pelo código SGS ou pelo slug."""
    if codigo_ou_slug in SERIES_POR_CODIGO:
        return SERIES_POR_CODIGO[codigo_ou_slug]
    if codigo_ou_slug in SERIES_POR_SLUG:
        return SERIES_POR_SLUG[codigo_ou_slug]
    raise KeyError(f"Série desconhecida: {codigo_ou_slug!r}")


@dataclass(frozen=True)
class Configuracoes:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg2://admin:securepassword@localhost:5432/bcb_dw")
    url_base_sgs: str = os.getenv("BCB_URL_BASE", "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados")
    # Limite imposto pelo BCB desde mar/2025: no máximo 10 anos por requisição.
    anos_por_janela: int = 10
    timeout_segundos: int = int(os.getenv("BCB_TIMEOUT", "60"))
    tentativas: int = int(os.getenv("BCB_TENTATIVAS", "5"))
    backoff_inicial_segundos: float = float(os.getenv("BCB_BACKOFF", "1.5"))
    log_nivel: str = os.getenv("LOG_LEVEL", "INFO")


CONFIG = Configuracoes()
