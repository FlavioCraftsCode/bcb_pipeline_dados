# Monitor Macro: pipeline de dados e Data Warehouse de indicadores do Banco Central

[![CI](https://github.com/FlavioCraftsCode/bcb_pipeline_dados/actions/workflows/ci.yml/badge.svg)](https://github.com/FlavioCraftsCode/bcb_pipeline_dados/actions/workflows/ci.yml)
[![Pipeline diária](https://github.com/FlavioCraftsCode/bcb_pipeline_dados/actions/workflows/pipeline-diaria.yml/badge.svg)](https://github.com/FlavioCraftsCode/bcb_pipeline_dados/actions/workflows/pipeline-diaria.yml)

**Painel ao vivo:** https://flaviocraftscode.github.io/bcb_pipeline_dados/ (atualizado todo dia pela própria pipeline)

Pipeline de dados de ponta a ponta sobre a API pública do SGS do Banco Central. Ela extrai sete indicadores
macroeconômicos, valida a qualidade de cada lote, carrega um Data Warehouse dimensional no PostgreSQL de forma
incremental e idempotente, calcula métricas analíticas, prevê o IPCA com backtest e entrega tudo por uma API REST e
um painel web.

> **English summary.** End-to-end data pipeline on the Brazilian Central Bank's public time-series API: incremental,
> idempotent loads into a PostgreSQL star schema; a data-quality layer that quarantines bad batches and reconciles
> computed vs. official inflation; versioned migrations and run observability; a 12-month CPI forecast selected by
> walk-forward backtesting against naive baselines; a FastAPI service; and a React/TypeScript/D3 dashboard deployed
> daily to GitHub Pages by a scheduled workflow that persists the warehouse between runs.

---

## O que este projeto demonstra

| Área | Como aparece aqui |
|---|---|
| Engenharia de dados | Extração em janelas de 10 anos (limite do SGS), retry com backoff exponencial e *jitter*, **carga incremental com janela de revisão** e **upsert idempotente** que distingue linha nova de dado revisado pela fonte |
| Modelagem | Star Schema (`fato_indicadores`, `dim_tempo`, `dim_indicador`) com **migrações versionadas** e marts analíticos em SQL (`mart_mensal`, `mart_juro_real`) |
| Qualidade de dados | Sete checagens por série classificadas como **bloqueantes** ou **informativas**, um **Circuito de Proteção de Dados** que isola automaticamente lotes inválidos da API externa e a **reconciliação** do IPCA 12 meses calculado contra a série oficial |
| Observabilidade | Cada execução fica registrada (`etl_execucoes`, `etl_execucoes_series`, `dq_resultados`): duração, linhas novas e revisadas, requisições HTTP e erros |
| Ciência de dados | Previsão do IPCA com 4 modelos, **backtest walk-forward sem vazamento**, comparação com *baselines* e intervalos de previsão empíricos com cobertura medida |
| Back-end | API REST com FastAPI e documentação OpenAPI em `/docs` |
| Front-end | Painel em React, TypeScript e D3, com gráficos próprios, tema escuro, navegação por teclado e paleta validada para daltonismo |
| DevOps | Docker multi-stage, Docker Compose, CI com testes de integração em PostgreSQL real e pipeline agendada no GitHub Actions |

## Arquitetura

```mermaid
flowchart LR
    SGS[(API SGS<br/>Banco Central)] -->|janelas de 10 anos<br/>retry + backoff| E[Extração]
    E --> T[Transformação]
    T --> Q{Qualidade<br/>7 checagens}
    Q -->|aprovado| C[Carga<br/>upsert idempotente]
    Q -->|bloqueante| X[Quarentena<br/>Circuito de Proteção de Dados]
    C --> DW[(PostgreSQL<br/>Star Schema)]
    DW --> M[Marts SQL<br/>juro real, mensal]
    DW --> P[Previsão IPCA<br/>backtest walk-forward]
    P --> DW
    DW --> API[FastAPI]
    API --> UI[Painel React + D3]
    DW -->|exportação JSON| GH[GitHub Pages]
```

### Modelo de dados

```mermaid
erDiagram
    dim_indicador ||--o{ fato_indicadores : ""
    dim_tempo ||--o{ fato_indicadores : ""
    etl_execucoes ||--o{ etl_execucoes_series : ""
    etl_execucoes ||--o{ dq_resultados : ""
    dim_indicador {
        int id_indicador PK
        varchar codigo_bcb UK
        varchar slug UK
        varchar nome_indicador
        varchar unidade
        varchar periodicidade
    }
    dim_tempo {
        int id_tempo PK
        date data UK
        int ano
        int mes
        int trimestre
        varchar dia_semana
        bool fim_de_mes
    }
    fato_indicadores {
        int id_fato PK
        int id_indicador FK
        int id_tempo FK
        numeric valor
        timestamptz carregado_em
        timestamptz atualizado_em
        int id_execucao
    }
    etl_execucoes {
        int id_execucao PK
        varchar status
        varchar modo
        int linhas_inseridas
        int linhas_revisadas
    }
```

A chave única `(id_indicador, id_tempo)` sustenta o upsert. Só são regravadas as linhas cujo valor mudou, e o
`RETURNING (xmax = 0)` do PostgreSQL separa inserções de revisões, que aparecem como métrica de cada execução.

## Indicadores

| Código SGS | Indicador | Periodicidade | Janela de revisão |
|---|---|---|---|
| 432 | Meta Selic (Copom) | diária | 10 dias úteis |
| 433 | IPCA, variação mensal | mensal | 3 meses |
| 13522 | IPCA acumulado em 12 meses (oficial, usado na reconciliação) | mensal | 3 meses |
| 189 | IGP-M, variação mensal | mensal | 3 meses |
| 1 | Dólar PTAX, venda | diária | 10 dias úteis |
| 24364 | IBC-Br dessazonalizado | mensal | 24 meses |
| 24369 | Taxa de desocupação (PNAD Contínua) | mensal | 3 meses |

Adicionar um indicador é uma entrada no catálogo em [`src/bcb_pipeline/config.py`](src/bcb_pipeline/config.py).
Extração, qualidade, carga, API e painel passam a tratá-lo sem outras mudanças.

> **Correção em relação à fase 1:** a série 11 do SGS é a Selic *diária* (% ao dia), não a meta definida pelo
> Copom. A meta é a série 432. A migração `002` remove os registros antigos e a pipeline carrega a série correta.

## Qualidade de dados

Cada regra tem uma severidade de governança:

- **Bloqueante:** o lote viola uma regra de integridade e não entra no Data Warehouse.
- **Informativo:** a anomalia é registrada para observabilidade e o lote segue normalmente.

| Checagem | Severidade | O que verifica |
|---|---|---|
| `nao_vazio` | Bloqueante (carga completa) | a API devolveu dados; em carga incremental, "nada novo" é normal |
| `sem_nulos` | Bloqueante | todas as datas e valores foram convertidos |
| `sem_duplicados` | Bloqueante | uma observação por data |
| `faixa_valida` | Bloqueante | valores dentro da faixa plausível do indicador |
| `reconciliacao_ipca_12m` | Bloqueante | IPCA 12m recalculado a partir do mensal bate com a série oficial (tolerância de 0,05 p.p.) |
| `atualidade` | Informativo | último dado dentro do atraso esperado de divulgação |
| `sem_lacunas` | Informativo | nenhum mês faltando em séries mensais |
| `outliers` | Informativo | variações recentes com z-score robusto (mediana/MAD) acima de 8 |

### Circuito de Proteção de Dados

A API do SGS é uma fonte externa: pode devolver valores corrompidos, lacunas ou ficar fora do ar. A pipeline trata
cada série como uma unidade isolada e valida o lote **antes** de qualquer escrita no Data Warehouse.

- **Isolamento automático de lotes da API externa.** Quando uma checagem bloqueante dispara, o lote daquela série
  é barrado na origem e fica em quarentena. Nenhuma linha dele é gravada.
- **Integridade do Data Warehouse preservada.** O histórico já carregado da série permanece intacto, e o painel e
  a API continuam servindo a última versão validada.
- **Continuidade das demais séries.** Um indicador isolado não impede a carga dos outros.
- **Rastreabilidade.** Cada isolamento fica registrado em `dq_resultados` e `etl_execucoes_series`, com a regra
  acionada e o detalhe do valor que a violou.

Status registrados em cada nível (fonte única em [`src/bcb_pipeline/status.py`](src/bcb_pipeline/status.py)):

| Nível | Status |
|---|---|
| Checagem | `ok`, `informativo`, `bloqueante` |
| Série | `sucesso`, `quarentena` (lote isolado), `interrompida` (fonte indisponível após as novas tentativas) |
| Execução | `sucesso`, `concluido_com_isolamento` (ao menos uma série isolada, as demais carregadas), `interrompida` (incidente operacional: a execução não chegou ao fim) |

`concluido_com_isolamento` significa que o circuito funcionou como projetado. `interrompida` fica reservado a
incidentes de infraestrutura, que continuam visíveis como tal no painel e encerram a CLI com código de saída 1.

## Previsão do IPCA

1. **Candidatos:** dois *baselines* honestos (ingênuo sazonal e média sazonal) e dois modelos de ML (Ridge e
   gradient boosting sobre 12 defasagens e sazonalidade, com previsão recursiva).
2. **Backtest walk-forward:** em cada uma das últimas 36+ datas, o modelo treina só com o passado e prevê 12 meses
   à frente, exatamente como teria feito em tempo real.
3. **Seleção** pelo menor MAE médio nos horizontes de 1 a 12 meses, reportando o *skill* contra o ingênuo sazonal
   e o erro no acumulado de 12 meses.
4. **Intervalos de 80%** a partir dos quantis dos erros do backtest por horizonte, sem supor normalidade, com a
   cobertura empírica medida e exibida no painel.

O resultado mostrado pode ser um *baseline*: se um modelo de ML não supera a referência simples no backtest, ele
não é usado. Isso é intencional.

## Como executar

### Com Docker (mais simples)

```bash
docker compose up --build
```

Isso sobe o PostgreSQL, roda a pipeline uma vez (a primeira carga baixa o histórico completo, em 1 a 2 minutos) e
serve o painel em **http://localhost:8000**, com a API documentada em **http://localhost:8000/docs**.

Para atualizar os dados depois: `docker compose run --rm etl`.

### Localmente

Pré-requisitos: Python 3.10+, Node 20+ e Docker (só para o PostgreSQL).

```bash
pip install -r requirements-dev.txt
docker compose up -d postgres_dw
cp .env.example .env                        # ajuste se necessário

# pipeline (PowerShell: $env:PYTHONPATH="src")
export PYTHONPATH=src
python -m bcb_pipeline executar             # incremental; completa no primeiro uso
python -m bcb_pipeline executar --completo  # recoleta tudo (idempotente)
python -m bcb_pipeline series               # lista o catálogo

# painel + API
cd frontend && npm install && npm run build && cd ..
uvicorn bcb_api.main:app --reload --app-dir src
```

Para desenvolver o front-end com recompilação automática: `cd frontend && npm run dev`.

### Testes

```bash
pytest -m "not integracao"   # unitários, sem banco nem rede
```

Os testes de integração rodam a pipeline inteira contra um PostgreSQL real, com a API do BCB substituída por uma
sessão falsa determinística. Eles cobrem a carga completa, a reexecução idempotente, a captura de revisões, a
quarentena (isolamento pelo Circuito de Proteção de Dados) e as rotas da API:

```bash
docker compose up -d postgres_dw
docker exec bcb_data_warehouse createdb -U admin bcb_test
DATABASE_URL_TESTE=postgresql+psycopg2://admin:securepassword@localhost:5432/bcb_test pytest -m integracao
```

O teste recria o schema do banco apontado em `DATABASE_URL_TESTE`, por isso ele usa uma variável própria e
nunca o `DATABASE_URL`. No CI, ambos os conjuntos rodam a cada push.

## Painel publicado e automação

O workflow [`pipeline-diaria.yml`](.github/workflows/pipeline-diaria.yml) roda todo dia às 07:17 (Brasília):

1. restaura o Data Warehouse do dia anterior (dump no cache do GitHub Actions);
2. roda a carga **incremental**;
3. salva o banco de volta;
4. exporta um snapshot JSON (`python -m bcb_pipeline exportar`) e publica o painel no GitHub Pages.

Por isso o histórico de execuções e de qualidade mostrado no painel é real, e não um exemplo. Para ativar, vá em
*Settings → Pages → Source: GitHub Actions* e rode o workflow manualmente uma vez.

## API

| Rota | Conteúdo |
|---|---|
| `GET /api/indicadores` | catálogo com último valor, valor de 12 meses atrás e minigráfico |
| `GET /api/series/{slug}?frequencia=mensal\|diaria&desde=aaaa-mm-dd` | série histórica |
| `GET /api/painel` | painel mensal com juro real, acumulados e variações em 12 meses |
| `GET /api/correlacoes` | matriz de correlação de Spearman |
| `GET /api/destaques?limite=8` | últimas mudanças da meta Selic e posição do IPCA em 12 meses frente à banda da meta de inflação |
| `GET /api/previsao` | previsão do IPCA, intervalos e métricas do backtest |
| `GET /api/qualidade` | resultados de qualidade da última execução e frescor das séries |
| `GET /api/execucoes` | histórico de execuções da pipeline |
| `GET /api/saude` | verificação de banco e última execução (sempre `no-store`) |

Datas inválidas em `desde` devolvem 422 (e não 500). As demais leituras saem com `Cache-Control: public, max-age=60`.

## Estrutura

```
├── database/migrations/      # 001 (fase 1), 002 (fase 2) e 003 (vocabulário de governança), aplicadas automaticamente
├── src/
│   ├── bcb_pipeline/
│   │   ├── config.py         # catálogo de séries e parâmetros
│   │   ├── extracao.py       # cliente SGS: janelas, retry, incremental
│   │   ├── transformacao.py  # formato canônico e dim_tempo
│   │   ├── qualidade.py      # checagens e reconciliação
│   │   ├── status.py         # vocabulário de status (checagem, série, execução)
│   │   ├── carga.py, sql.py  # upsert no Star Schema e registros de execução
│   │   ├── analise.py        # acumulados, juro real, correlações
│   │   ├── previsao.py       # modelos, backtest e intervalos
│   │   ├── consultas.py      # camada de leitura usada pela API e pela exportação
│   │   ├── pipeline.py       # orquestração
│   │   └── __main__.py       # CLI
│   └── bcb_api/              # FastAPI (main.py), contratos de resposta (schemas.py) e servidor do painel
├── frontend/                 # React + TypeScript + D3, build com esbuild
├── tests/                    # unitários e de integração
└── .github/workflows/        # CI e pipeline diária
```

## Decisões de projeto

- **Migrações em vez de `DROP TABLE`.** A fase 1 recriava o banco a cada execução. Agora o histórico é preservado,
  as mudanças de esquema são versionadas e um banco da fase 1 é atualizado no lugar.
- **Janela de revisão por série.** O IBC-Br dessazonalizado muda meses depois de publicado. Recoletar só o último
  dado perderia essas revisões, e recoletar tudo seria desperdício.
- **Z-score robusto.** O histórico brasileiro tem caudas pesadíssimas (planos econômicos). Com desvio-padrão, um
  dado novo anômalo passaria despercebido; mediana e MAD não se deixam contaminar.
- **Camada de leitura única.** A API e o snapshot estático usam as mesmas funções, então o painel ao vivo e o
  publicado mostram exatamente os mesmos números.
- **Gráficos próprios com D3.** Controle total de acessibilidade (teclado, tooltips que não são o único acesso ao
  valor, tabela e CSV) e de semântica visual (degrau para a Selic, faixa sombreada para o juro real).

## Próximos passos

- Expectativas do boletim Focus como regressoras da previsão
- Orquestração com Airflow ou Dagster e notificação de lotes isolados por e-mail
- Camada de transformação em dbt para os marts

---

Dados: [SGS / Banco Central do Brasil](https://www3.bcb.gov.br/sgspub/). Projeto independente, sem vínculo com o BCB.
