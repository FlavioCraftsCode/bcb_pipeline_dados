# Pipeline de Dados e Modelagem Econômica (BCB)

Pipeline de Engenharia de Dados desenvolvido para extração, tratamento, modelagem dimensional (Star Schema) e carga de indicadores macroeconômicos oficiais extraídos diretamente da API do Banco Central do Brasil (SGS).

---

## 🛠 Tecnologias Utilizadas
* **Python** (Requests, Pandas, SQLAlchemy)
* **PostgreSQL** (Armazenamento e Data Warehouse local)
* **Docker & Docker Compose** (Isolamento de ambiente e infraestrutura)
* **Git & GitHub** (Versionamento de código)

---

## 📐 Arquitetura do Projeto
O fluxo de dados segue uma arquitetura corporativa de ponta a ponta:
1. **Extração:** Consumo automatizado da API REST pública do SGS (Taxa Selic, IPCA e Dólar).
2. **Transformação:** Limpeza de tipos, padronização de datas (tratamento de *strings* para formato temporal) e engenharia de atributos de tempo.
3. **Carga e Modelagem:** Organização dos dados em um modelo relacional dimensional (**Star Schema**) contendo tabelas de Dimensão (`dim_tempo`, `dim_indicador`) e Tabela Fato (`fato_indicadores`).

---

## 🚀 Como Executar o Projeto Localmente

### Pré-requisitos
* Python 3.10+ instalado
* Docker e Docker Compose instalados

### Passo a passo
1. Clone o repositório:
   ```bash
   git clone [https://github.com/FlavioCraftsCode/bcb_pipeline_dados.git](https://github.com/FlavioCraftsCode/bcb_pipeline_dados.git)
   cd bcb_pipeline_dados