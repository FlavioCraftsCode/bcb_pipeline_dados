import os
import pandas as pd
import requests
from sqlalchemy import create_engine, text

DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://admin:securepassword@localhost:5432/bcb_dw"
)
engine = create_engine(DB_URL)

SERIES = {
    "11": "Taxa Selic Meta",
    "433": "IPCA - Variacao Mensal",
    "1": "Taxa de Cambio - Dolar (Venda)",
}

# Desde mar/2025 a API SGS do BCB limita consultas de séries diárias a uma
# janela de no máximo 10 anos por requisição (sem datas, retorna HTTP 406).
# Por isso a extração é feita em blocos de até 10 anos.
DATA_INICIO_PADRAO = os.getenv("BCB_DATA_INICIO", "01/01/1980")
ANOS_POR_JANELA = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _gerar_janelas(inicio: pd.Timestamp, fim: pd.Timestamp):
  atual = inicio
  while atual <= fim:
    proximo = atual + pd.DateOffset(years=ANOS_POR_JANELA) - pd.Timedelta(days=1)
    yield atual, min(proximo, fim)
    atual = proximo + pd.Timedelta(days=1)


def extrair_dados_bcb(codigo_serie: str) -> pd.DataFrame:
  url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo_serie}/dados"
  inicio = pd.to_datetime(DATA_INICIO_PADRAO, format="%d/%m/%Y")
  fim = pd.Timestamp.today().normalize()

  blocos = []
  for ini, fi in _gerar_janelas(inicio, fim):
    params = {
        "formato": "json",
        "dataInicial": ini.strftime("%d/%m/%Y"),
        "dataFinal": fi.strftime("%d/%m/%Y"),
    }
    response = requests.get(url, headers=HEADERS, params=params, timeout=60)

    # 404 = nenhum dado na janela (ex.: período anterior ao início da série)
    if response.status_code == 404:
      continue
    if response.status_code != 200:
      raise Exception(
          f"Erro ao acessar API do BCB para a série {codigo_serie}"
          f" ({params['dataInicial']} a {params['dataFinal']})."
          f" Status: {response.status_code} - {response.text[:200]}"
      )

    dados = response.json()
    if dados:
      blocos.append(pd.DataFrame(dados))

  if not blocos:
    raise Exception(f"Nenhum dado retornado pela API do BCB para a série {codigo_serie}.")

  return (
      pd.concat(blocos, ignore_index=True)
      .drop_duplicates(subset=["data"])
      .reset_index(drop=True)
  )

def transformar_dados(df: pd.DataFrame, nome_indicador: str, codigo_serie: str) -> pd.DataFrame:
  df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
  df["valor"] = pd.to_numeric(df["valor"].str.replace(",", "."), errors="coerce")
  df["indicador"] = nome_indicador
  df["codigo_bcb"] = codigo_serie
  
  df["ano"] = df["data"].dt.year
  df["mes"] = df["data"].dt.month
  df["trimestre"] = df["data"].dt.quarter
  df["dia_semana"] = df["data"].dt.day_name()
  
  return df

def executar_etl():
  print("Iniciando pipeline de dados do Banco Central (Star Schema)...")
  
  schema_path = os.path.join("database", "schema.sql")
  if os.path.exists(schema_path):
    print("Aplicando modelo dimensional (schema.sql)...")
    with open(schema_path, "r", encoding="utf-8") as f:
      sql_script = f.read()
    with engine.begin() as conn:
      for statement in sql_script.split(";"):
        if statement.strip():
          conn.execute(text(statement))

  dados_processados = []

  for codigo, nome in SERIES.items():
    print(f"Extraindo: {nome} (Código: {codigo})...")
    df_raw = extrair_dados_bcb(codigo)
    df_clean = transformar_dados(df_raw, nome, codigo)
    dados_processados.append(df_clean)

  df_final = pd.concat(dados_processados, ignore_index=True)

  df_indicadores = (
      df_final[["indicador", "codigo_bcb"]]
      .drop_duplicates()
      .rename(columns={"indicador": "nome_indicador"})
      .reset_index(drop=True)
  )
  df_indicadores.to_sql("dim_indicador", con=engine, if_exists="append", index=False)

  df_tempo = df_final[["data", "ano", "mes", "trimestre", "dia_semana"]].drop_duplicates().reset_index(drop=True)
  df_tempo.to_sql("dim_tempo", con=engine, if_exists="append", index=False)

  with engine.connect() as conn:
    dim_tempo_db = pd.read_sql("SELECT id_tempo, data FROM dim_tempo", conn)
    dim_indicador_db = pd.read_sql("SELECT id_indicador, nome_indicador FROM dim_indicador", conn)

  dim_tempo_db["data"] = pd.to_datetime(dim_tempo_db["data"])

  df_fato = df_final.merge(dim_tempo_db, on="data", how="left")
  df_fato = df_fato.merge(dim_indicador_db, left_on="indicador", right_on="nome_indicador", how="left")

  df_fato_final = df_fato[["id_tempo", "id_indicador", "valor"]].dropna()

  print("Carregando dados na tabela fato...")
  df_fato_final.to_sql("fato_indicadores", con=engine, if_exists="append", index=False)

  print("Pipeline executado com sucesso e modelado em Star Schema!")

if __name__ == "__main__":
  executar_etl()