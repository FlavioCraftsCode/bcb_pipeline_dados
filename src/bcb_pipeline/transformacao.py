"""Transformação: dados brutos do SGS -> formato canônico.

Formato canônico (uma linha por série e data)::

    codigo_bcb | data (datetime64) | valor (float)
"""

from __future__ import annotations

import pandas as pd

from .config import Serie

DIAS_SEMANA_PT = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}


def para_numero(valores: pd.Series) -> pd.Series:
    """Converte valores do SGS em float.

    A API usa ponto decimal no JSON, mas alguns exports usam vírgula; tratamos
    os dois. Valores inválidos viram NaN e são barrados pela camada de qualidade.
    """
    texto = valores.astype("string").str.strip()
    tem_virgula = texto.str.contains(",", regex=False, na=False)
    texto = texto.where(~tem_virgula, texto.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(texto, errors="coerce").astype("float64")


def transformar(df_bruto: pd.DataFrame, serie: Serie) -> pd.DataFrame:
    if df_bruto.empty:
        return pd.DataFrame(
            {
                "codigo_bcb": pd.Series(dtype="string"),
                "data": pd.Series(dtype="datetime64[ns]"),
                "valor": pd.Series(dtype="float64"),
            }
        )
    df = pd.DataFrame(
        {
            "codigo_bcb": serie.codigo,
            "data": pd.to_datetime(df_bruto["data"], format="%d/%m/%Y", errors="coerce"),
            "valor": para_numero(df_bruto["valor"]),
        }
    )
    df["codigo_bcb"] = df["codigo_bcb"].astype("string")
    return df.sort_values("data").reset_index(drop=True)


def dimensao_tempo(datas: pd.Series) -> pd.DataFrame:
    """Gera as linhas da ``dim_tempo`` para um conjunto de datas."""
    d = pd.Series(pd.to_datetime(datas).dropna().unique()).sort_values().reset_index(drop=True)
    return pd.DataFrame(
        {
            "data": d.dt.date,
            "ano": d.dt.year.astype(int),
            "mes": d.dt.month.astype(int),
            "trimestre": d.dt.quarter.astype(int),
            "dia_semana": d.dt.dayofweek.map(DIAS_SEMANA_PT),
            "fim_de_mes": d.dt.is_month_end,
        }
    )
