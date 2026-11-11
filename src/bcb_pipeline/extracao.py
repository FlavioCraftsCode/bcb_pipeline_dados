"""Extração da API SGS do Banco Central.

Pontos de engenharia tratados aqui:

* **Janelas de 10 anos** — desde mar/2025 o SGS recusa consultas maiores.
* **Retry com backoff exponencial + jitter** para 429/5xx e falhas de rede;
  erros 4xx definitivos falham rápido.
* **Carga incremental** — recebe a última data já carregada e recoleta apenas um
  pequeno trecho de revisão (``Serie.periodos_revisao``), em vez de baixar
  40 anos de histórico a cada execução.
* A sessão HTTP e a função de espera são injetáveis, o que permite testar tudo
  sem rede.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date

import pandas as pd
import requests

from .config import CONFIG, Configuracoes, Periodicidade, Serie

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "bcb-pipeline-dados/2.0 (+https://github.com/FlavioCraftsCode/bcb_pipeline_dados)",
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

STATUS_TRANSITORIOS = {429, 500, 502, 503, 504}


class ErroExtracao(RuntimeError):
    """Falha definitiva ao extrair uma série."""


@dataclass
class EstatisticasExtracao:
    requisicoes: int = 0
    tentativas_extras: int = 0
    janelas_vazias: int = 0


def gerar_janelas(inicio: pd.Timestamp, fim: pd.Timestamp, anos: int) -> Iterator[tuple[pd.Timestamp, pd.Timestamp]]:
    """Divide [inicio, fim] em blocos contíguos de no máximo ``anos`` anos."""
    if inicio > fim:
        return
    atual = inicio
    while atual <= fim:
        proximo = atual + pd.DateOffset(years=anos) - pd.Timedelta(days=1)
        yield atual, min(proximo, fim)
        atual = proximo + pd.Timedelta(days=1)


def data_inicio_incremental(serie: Serie, ultima_data: date | None) -> pd.Timestamp:
    """Calcula de onde recomeçar a coleta.

    Sem histórico: começa no início da série. Com histórico: volta
    ``periodos_revisao`` períodos para recapturar dados revisados pela fonte.
    """
    inicio_serie = pd.to_datetime(serie.inicio, format="%d/%m/%Y")
    if ultima_data is None:
        return inicio_serie
    ultima = pd.Timestamp(ultima_data)
    if serie.periodicidade is Periodicidade.MENSAL:
        recuo = pd.DateOffset(months=serie.periodos_revisao)
    else:
        # dias úteis aproximados -> dias corridos com folga para fins de semana/feriados
        recuo = pd.Timedelta(days=int(serie.periodos_revisao * 1.6) + 3)
    return max(inicio_serie, (ultima - recuo).normalize())


class ClienteSGS:
    def __init__(
        self,
        config: Configuracoes = CONFIG,
        sessao: requests.Session | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update(HEADERS)
        self.dormir = dormir
        self.estatisticas = EstatisticasExtracao()

    # ------------------------------------------------------------------ HTTP
    def _get(self, url: str, params: dict[str, str]) -> list[dict] | None:
        """GET com retry. Retorna ``None`` quando a janela não tem dados (404)."""
        ultima_falha = ""
        for tentativa in range(1, self.config.tentativas + 1):
            self.estatisticas.requisicoes += 1
            try:
                resposta = self.sessao.get(url, params=params, timeout=self.config.timeout_segundos)
            except (requests.ConnectionError, requests.Timeout) as exc:
                ultima_falha = f"{type(exc).__name__}: {exc}"
            else:
                if resposta.status_code == 200:
                    return resposta.json() or None
                if resposta.status_code == 404:
                    return None
                if resposta.status_code not in STATUS_TRANSITORIOS:
                    raise ErroExtracao(f"HTTP {resposta.status_code} em {url} {params}: {resposta.text[:200]}")
                ultima_falha = f"HTTP {resposta.status_code}"

            if tentativa < self.config.tentativas:
                espera = self.config.backoff_inicial_segundos * 2 ** (tentativa - 1)
                espera *= random.uniform(0.8, 1.2)  # jitter evita rajadas sincronizadas
                self.estatisticas.tentativas_extras += 1
                log.warning("Falha transitória (%s). Nova tentativa em %.1fs.", ultima_falha, espera)
                self.dormir(espera)

        raise ErroExtracao(f"Esgotadas {self.config.tentativas} tentativas em {url}: {ultima_falha}")

    # --------------------------------------------------------------- público
    def extrair(
        self,
        serie: Serie,
        desde: pd.Timestamp | None = None,
        ate: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Retorna um DataFrame bruto com colunas ``data`` e ``valor`` (strings da API)."""
        url = self.config.url_base_sgs.format(codigo=serie.codigo)
        inicio = desde if desde is not None else pd.to_datetime(serie.inicio, format="%d/%m/%Y")
        fim = ate if ate is not None else pd.Timestamp.today().normalize()

        blocos: list[pd.DataFrame] = []
        for ini, fi in gerar_janelas(inicio, fim, self.config.anos_por_janela):
            params = {
                "formato": "json",
                "dataInicial": ini.strftime("%d/%m/%Y"),
                "dataFinal": fi.strftime("%d/%m/%Y"),
            }
            dados = self._get(url, params)
            if not dados:
                self.estatisticas.janelas_vazias += 1
                continue
            blocos.append(pd.DataFrame(dados))

        if not blocos:
            log.info("Série %s sem dados novos entre %s e %s.", serie.codigo, inicio.date(), fim.date())
            return pd.DataFrame(columns=["data", "valor"])

        df = pd.concat(blocos, ignore_index=True)
        return df.drop_duplicates(subset=["data"], keep="last").reset_index(drop=True)
