import { useDados } from "../api";
import { Carregando, Erro, Secao, Status } from "../componentes";
import { dataCurta, dataHora, inteiro } from "../formato";
import type { Qualidade as TQualidade, ResultadoQualidade, StatusCheck } from "../tipos";

const CHECAGENS: { chave: string; rotulo: string; explica: string }[] = [
  { chave: "nao_vazio", rotulo: "Recebeu dados", explica: "A API devolveu linhas (ou nada novo, em carga incremental)." },
  { chave: "sem_nulos", rotulo: "Sem nulos", explica: "Todas as datas e valores foram convertidos." },
  { chave: "sem_duplicados", rotulo: "Sem duplicatas", explica: "Uma observação por data." },
  { chave: "faixa_valida", rotulo: "Faixa válida", explica: "Valores dentro da faixa plausível do indicador." },
  { chave: "atualidade", rotulo: "Atualizada", explica: "Último dado dentro do atraso esperado de divulgação." },
  { chave: "sem_lacunas", rotulo: "Sem lacunas", explica: "Nenhum mês faltando em séries mensais." },
  { chave: "outliers", rotulo: "Sem outliers", explica: "Variações recentes com z-score robusto (mediana/MAD) até 8." },
];

const PESO: Record<StatusCheck, number> = { ok: 0, alerta: 1, falha: 2 };

export function Qualidade() {
  const { dados, erro } = useDados<TQualidade>("qualidade");
  if (erro) return <Erro mensagem={erro} />;
  if (!dados) return <Carregando />;
  if (!dados.resultados.length) return <p className="vazio">Nenhuma checagem registrada ainda.</p>;

  const porSerie = new Map<string, ResultadoQualidade[]>();
  dados.resultados.forEach((r) => {
    const k = r.codigo_bcb;
    porSerie.set(k, [...(porSerie.get(k) ?? []), r]);
  });
  const contagem = { ok: 0, alerta: 0, falha: 0 } as Record<StatusCheck, number>;
  dados.resultados.forEach((r) => (contagem[r.status] += 1));
  const atencao = dados.resultados
    .filter((r) => r.status !== "ok")
    .sort((a, b) => PESO[b.status] - PESO[a.status]);
  const reconc = dados.resultados.find((r) => r.checagem === "reconciliacao_ipca_12m");
  const verificado = dados.resultados[0]?.verificado_em ?? null;

  return (
    <>
      <header className="cabecalho-pagina">
        <h1>Qualidade de dados</h1>
        <p className="secao-descricao">
          Toda carga passa por estas checagens antes de entrar no Data Warehouse. Uma falha põe o lote da série em
          quarentena: o histórico já carregado é preservado e as demais séries seguem normalmente. Execução #
          {dados.id_execucao}, verificada em {dataHora(verificado)}.
        </p>
      </header>

      <div className="resumo-status" aria-label="Resumo das checagens">
        <Status status="ok" rotulo={`${contagem.ok} aprovadas`} />
        <Status status="alerta" rotulo={`${contagem.alerta} alertas`} />
        <Status status="falha" rotulo={`${contagem.falha} falhas`} />
      </div>

      <Secao titulo="Checagens por indicador" descricao="Passe o cursor sobre um ícone para ver o detalhe.">
        <div className="tabela-rolagem">
          <table className="tabela matriz-dq">
            <thead>
              <tr>
                <th scope="col">Indicador</th>
                {CHECAGENS.map((c) => (
                  <th key={c.chave} scope="col" title={c.explica}>
                    {c.rotulo}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...porSerie.entries()].map(([codigo, rs]) => {
                const nome = rs[0].nome_indicador ?? codigo;
                return (
                  <tr key={codigo}>
                    <th scope="row">
                      {nome}
                      <span className="sub">SGS {codigo}</span>
                    </th>
                    {CHECAGENS.map((c) => {
                      const r = rs.find((x) => x.checagem === c.chave);
                      return (
                        <td key={c.chave} title={r?.detalhe}>
                          {r ? <Status status={r.status} compacto rotulo={`${c.rotulo}: ${r.detalhe}`} /> : "—"}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Secao>

      <div className="duas-colunas">
        <Secao titulo="Pontos de atenção" descricao="Alertas e falhas da última execução, com o detalhe registrado.">
          {atencao.length === 0 ? (
            <p>Nenhum alerta. Todas as checagens passaram.</p>
          ) : (
            <ul className="lista-atencao">
              {atencao.map((r) => (
                <li key={`${r.codigo_bcb}-${r.checagem}`}>
                  <Status status={r.status} />
                  <div>
                    <strong>{r.nome_indicador ?? r.codigo_bcb}</strong>
                    <p>{r.detalhe}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Secao>
        <Secao
          titulo="Reconciliação com a fonte oficial"
          descricao="A pipeline recalcula o IPCA acumulado em 12 meses a partir das variações mensais e confere com a série oficial 13522. Se um único mês vier errado, o acumulado diverge."
        >
          {reconc ? (
            <div className="reconciliacao">
              <Status status={reconc.status} />
              <p>{reconc.detalhe}</p>
            </div>
          ) : (
            <p>Reconciliação ainda não executada.</p>
          )}
        </Secao>
      </div>

      <Secao titulo="Frescor das séries" descricao="Última observação disponível no Data Warehouse.">
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th scope="col">Indicador</th>
                <th scope="col">Periodicidade</th>
                <th scope="col">Último dado</th>
                <th scope="col" className="num">
                  Dias desde o último dado
                </th>
                <th scope="col" className="num">
                  Observações
                </th>
              </tr>
            </thead>
            <tbody>
              {dados.frescor.map((f) => (
                <tr key={f.codigo_bcb}>
                  <td>{f.nome_indicador}</td>
                  <td>{f.periodicidade === "diaria" ? "Diária" : "Mensal"}</td>
                  <td>{f.ultima_data ? dataCurta(f.ultima_data) : "—"}</td>
                  <td className="num">{inteiro(f.dias_desde_ultima)}</td>
                  <td className="num">{inteiro(f.observacoes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Secao>
    </>
  );
}
