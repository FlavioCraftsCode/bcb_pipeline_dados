import { useDados } from "../api";
import { Carregando, Erro, Secao, Status } from "../componentes";
import { dataCurta, dataHora, duracao, inteiro, num } from "../formato";
import type { Execucoes } from "../tipos";

const ETAPAS = [
  { titulo: "Extração", texto: "API SGS do Banco Central em janelas de 10 anos, com retry e backoff exponencial." },
  { titulo: "Transformação", texto: "Tipagem, datas, padronização e dimensão de calendário em português." },
  {
    titulo: "Qualidade",
    texto: "Sete checagens por série e reconciliação do IPCA. Lote bloqueado é isolado em quarentena na origem.",
  },
  { titulo: "Carga", texto: "Upsert idempotente no Star Schema do PostgreSQL, registrando revisões da fonte." },
  { titulo: "Análise e previsão", texto: "Marts mensais, juro real, correlações e previsão do IPCA com backtest." },
  { titulo: "Entrega", texto: "API REST com FastAPI e este painel, também publicado como site estático." },
];

const NOMES_SERIE: Record<string, string> = {
  selic: "Meta Selic",
  ipca: "IPCA mensal",
  ipca_12m: "IPCA 12 meses",
  igpm: "IGP-M",
  dolar: "Dólar",
  ibcbr: "IBC-Br",
  desemprego: "Desocupação",
};

export function Pipeline() {
  const { dados, erro } = useDados<Execucoes>("execucoes");
  if (erro) return <Erro mensagem={erro} />;
  if (!dados) return <Carregando />;
  const ultima = dados.execucoes[0];
  const ultimas = dados.execucoes.slice(0, 30);
  const concluidas = ultimas.filter((e) => e.status === "sucesso" || e.status === "concluido_com_isolamento");
  const comIsolamento = ultimas.filter((e) => e.status === "concluido_com_isolamento").length;
  const taxa = concluidas.length / Math.max(1, ultimas.length);

  return (
    <>
      <header className="cabecalho-pagina">
        <h1>Pipeline de dados</h1>
        <p className="secao-descricao">
          Roda todo dia de forma incremental: busca apenas o trecho recente de cada série (com uma janela de revisão,
          porque o IBGE e o BCB revisam dados passados) e grava só o que mudou. Cada série é processada de forma
          isolada: um lote bloqueado ou uma fonte indisponível não impede a carga das demais.
        </p>
      </header>

      <ol className="fluxo" aria-label="Etapas da pipeline">
        {ETAPAS.map((e) => (
          <li key={e.titulo}>
            <strong>{e.titulo}</strong>
            <span>{e.texto}</span>
          </li>
        ))}
      </ol>

      {ultima && (
        <div className="faixa-kpis">
          <div>
            <span className="kpi-rotulo">Última execução</span>
            <span className="kpi-valor kpi-texto">
              <Status status={ultima.status} />
            </span>
            <span className="kpi-nota">
              #{ultima.id_execucao}, {dataHora(ultima.iniciado_em)}, {ultima.modo}
            </span>
          </div>
          <div>
            <span className="kpi-rotulo">Duração</span>
            <span className="kpi-valor">{duracao(ultima.duracao_s)}</span>
            <span className="kpi-nota">{inteiro(ultima.requisicoes_http)} requisições HTTP</span>
          </div>
          <div>
            <span className="kpi-rotulo">Linhas novas e revisadas</span>
            <span className="kpi-valor">
              {inteiro(ultima.linhas_inseridas)} <span className="kpi-sep">/</span> {inteiro(ultima.linhas_revisadas)}
            </span>
            <span className="kpi-nota">de {inteiro(ultima.linhas_extraidas)} linhas extraídas</span>
          </div>
          <div>
            <span className="kpi-rotulo">Execuções concluídas</span>
            <span className="kpi-valor">{num(taxa * 100, 0)}%</span>
            <span className="kpi-nota">
              das últimas {ultimas.length}; {comIsolamento} com isolamento de lotes
            </span>
          </div>
        </div>
      )}

      <Secao titulo="Última execução por série">
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th scope="col">Série</th>
                <th scope="col">Status</th>
                <th scope="col">Coletado desde</th>
                <th scope="col" className="num">
                  Extraídas
                </th>
                <th scope="col" className="num">
                  Novas
                </th>
                <th scope="col" className="num">
                  Revisadas
                </th>
                <th scope="col" className="num">
                  Tempo
                </th>
              </tr>
            </thead>
            <tbody>
              {dados.ultima_por_serie.map((s) => (
                <tr key={s.codigo_bcb}>
                  <td>
                    {NOMES_SERIE[s.slug ?? ""] ?? s.codigo_bcb}
                    <span className="sub">SGS {s.codigo_bcb}</span>
                  </td>
                  <td>
                    <Status status={s.status} />
                    {s.erro && <span className="sub">{s.erro}</span>}
                  </td>
                  <td>{s.desde ? dataCurta(s.desde) : "—"}</td>
                  <td className="num">{inteiro(s.linhas_extraidas)}</td>
                  <td className="num">{inteiro(s.linhas_inseridas)}</td>
                  <td className="num">{inteiro(s.linhas_revisadas)}</td>
                  <td className="num">{duracao(s.duracao_ms / 1000)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Secao>

      <Secao titulo="Histórico de execuções">
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th scope="col">Execução</th>
                <th scope="col">Início</th>
                <th scope="col">Status</th>
                <th scope="col">Modo</th>
                <th scope="col" className="num">
                  Duração
                </th>
                <th scope="col" className="num">
                  Novas
                </th>
                <th scope="col" className="num">
                  Revisadas
                </th>
                <th scope="col">Observação</th>
              </tr>
            </thead>
            <tbody>
              {dados.execucoes.map((e) => (
                <tr key={e.id_execucao}>
                  <td>#{e.id_execucao}</td>
                  <td>{dataHora(e.iniciado_em)}</td>
                  <td>
                    <Status status={e.status} />
                  </td>
                  <td>{e.modo}</td>
                  <td className="num">{duracao(e.duracao_s)}</td>
                  <td className="num">{inteiro(e.linhas_inseridas)}</td>
                  <td className="num">{inteiro(e.linhas_revisadas)}</td>
                  <td className="observacao">{e.erro ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Secao>
    </>
  );
}
