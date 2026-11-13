// Contratos das respostas da API (espelham bcb_pipeline/consultas.py).

export interface Ponto {
  data: string;
  valor: number | null;
}

export interface Resumo {
  data: string;
  valor: number;
  anterior: number | null;
  valor_12m_atras: number | null;
  min_5a: number;
  max_5a: number;
  observacoes: number;
  periodicidade: string;
}

export interface Indicador {
  codigo: string;
  slug: string;
  nome: string;
  unidade: string;
  periodicidade: "diaria" | "mensal";
  fonte: string;
  descricao: string;
  casas_decimais: number;
  tags: string[];
  resumo: Resumo;
  faisca: Ponto[];
}

export interface SerieHistorica {
  slug: string;
  codigo: string;
  nome: string;
  unidade: string;
  frequencia: "mensal" | "diaria";
  pontos: Ponto[];
}

export type LinhaPainel = { data: string } & Record<string, number | null | string>;

export interface Painel {
  colunas: Record<string, string>;
  ultimo: Record<string, Ponto | null>;
  linhas: LinhaPainel[];
}

export interface Correlacoes {
  metodo: string;
  desde: string;
  rotulos: Record<string, string>;
  variaveis: string[];
  matriz: (number | null)[][];
}

export interface PontoPrevisao {
  data: string;
  horizonte: number;
  previsto: number;
  li: number;
  ls: number;
  previsto_12m: number;
  li_12m: number;
  ls_12m: number;
}

export interface MetricaModelo {
  modelo: string;
  escolhido: boolean;
  mae: number;
  rmse: number;
  mae_12m: number | null;
  skill: number | null;
  origens: number;
  cobertura: number | null;
  descricao: string;
}

export interface Previsao {
  disponivel: boolean;
  gerado_em?: string;
  modelo?: string;
  data_base?: string;
  nivel_intervalo?: number;
  previsao?: PontoPrevisao[];
  metricas?: MetricaModelo[];
  historico?: { data: string; ipca: number | null; ipca_12m: number | null }[];
}

// Vocabulário de governança (espelha bcb_pipeline/status.py).
export type StatusCheck = "ok" | "informativo" | "bloqueante";

export interface ResultadoQualidade {
  codigo_bcb: string;
  slug: string | null;
  nome_indicador: string | null;
  checagem: string;
  status: StatusCheck;
  detalhe: string;
  valor_observado: number | null;
  verificado_em: string;
}

export interface Frescor {
  codigo_bcb: string;
  slug: string;
  nome_indicador: string;
  periodicidade: string;
  ultima_data: string | null;
  observacoes: number;
  ultima_atualizacao: string | null;
  dias_desde_ultima: number | null;
}

export interface Qualidade {
  id_execucao: number | null;
  resultados: ResultadoQualidade[];
  frescor: Frescor[];
  historico?: { id_execucao: number; ok: number; informativo: number; bloqueante: number }[];
}

export type StatusExecucao = "executando" | "sucesso" | "concluido_com_isolamento" | "interrompida";

export type StatusSerie = "sucesso" | "quarentena" | "interrompida";

export interface Execucao {
  id_execucao: number;
  iniciado_em: string;
  finalizado_em: string | null;
  status: StatusExecucao;
  modo: string;
  gatilho: string;
  linhas_extraidas: number;
  linhas_inseridas: number;
  linhas_revisadas: number;
  requisicoes_http: number;
  erro: string | null;
  duracao_s: number | null;
}

export interface ExecucaoSerie {
  id_execucao: number;
  codigo_bcb: string;
  slug: string | null;
  status: StatusSerie;
  desde: string | null;
  linhas_extraidas: number;
  linhas_inseridas: number;
  linhas_revisadas: number;
  duracao_ms: number;
  erro: string | null;
}

export interface Execucoes {
  execucoes: Execucao[];
  ultima_por_serie: ExecucaoSerie[];
}

export interface Meta {
  gerado_em: string;
  modo: string;
}

export interface DecisaoSelic {
  data: string;
  de: number;
  para: number;
  variacao_pp: number;
}

export interface MetaInflacao {
  data: string;
  ipca_12m: number;
  meta: number;
  piso: number;
  teto: number;
  desvio_pp: number;
  situacao: "dentro" | "acima" | "abaixo";
  meses_consecutivos_fora: number;
  meses_para_descumprimento: number;
}

export interface Destaques {
  selic: { data: string; atual: number | null; dias_desde_ultima_mudanca: number; decisoes: DecisaoSelic[] } | null;
  meta_inflacao: MetaInflacao | null;
}
