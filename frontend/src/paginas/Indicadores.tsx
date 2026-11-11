import { useEffect, useMemo, useState } from "react";
import { useDados } from "../api";
import { Carregando, Erro, Segmentado } from "../componentes";
import { corSerie } from "../cores";
import { dataCurta, inteiro, mesAno, num, paraData } from "../formato";
import { GraficoLinhas, type PontoXY } from "../graficos/GraficoLinhas";
import type { Indicador, SerieHistorica } from "../tipos";

type Janela = "2" | "5" | "10" | "tudo";
type Transf = "nivel" | "var12" | "acum12";

function lerSerieDaUrl(): string | null {
  const q = window.location.hash.split("?")[1];
  return q ? new URLSearchParams(q).get("serie") : null;
}

/** Transformações calculadas no cliente sobre a série mensal. */
function transformar(pontos: PontoXY[], t: Transf): PontoXY[] {
  if (t === "nivel") return pontos;
  return pontos.map((p, i) => {
    if (i < 12) return { x: p.x, y: null };
    const janela = pontos.slice(i - 11, i + 1);
    if (t === "acum12") {
      if (janela.some((d) => d.y === null)) return { x: p.x, y: null };
      const f = janela.reduce((acc, d) => acc * (1 + (d.y as number) / 100), 1);
      return { x: p.x, y: (f - 1) * 100 };
    }
    const ant = pontos[i - 12].y;
    return { x: p.x, y: p.y !== null && ant ? (p.y / ant - 1) * 100 : null };
  });
}

function opcoesTransf(ind: Indicador): { valor: Transf; rotulo: string }[] | null {
  if (ind.slug === "ipca" || ind.slug === "igpm")
    return [
      { valor: "nivel", rotulo: "No mês" },
      { valor: "acum12", rotulo: "Acumulado 12 meses" },
    ];
  if (ind.slug === "dolar" || ind.slug === "ibcbr")
    return [
      { valor: "nivel", rotulo: "Nível" },
      { valor: "var12", rotulo: "Variação 12 meses" },
    ];
  return null;
}

function baixarCsv(nome: string, pontos: PontoXY[]) {
  const linhas = ["data;valor", ...pontos.map((p) => `${p.x.toISOString().slice(0, 10)};${p.y ?? ""}`)];
  const blob = new Blob([`﻿${linhas.join("\n")}`], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${nome}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function Indicadores() {
  const lista = useDados<Indicador[]>("indicadores");
  const [slug, setSlug] = useState<string>(lerSerieDaUrl() ?? "selic");
  const [janela, setJanela] = useState<Janela>("10");
  const [transf, setTransf] = useState<Transf>("nivel");
  const [tabela, setTabela] = useState(false);

  useEffect(() => {
    const f = () => {
      const s = lerSerieDaUrl();
      if (s) setSlug(s);
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  const ind = lista.dados?.find((i) => i.slug === slug) ?? null;
  const diaria = ind?.periodicidade === "diaria" && (janela === "2" || janela === "5") && transf === "nivel";
  const serie = useDados<SerieHistorica>(`series/${slug}`, { frequencia: diaria ? "diaria" : "mensal" });

  const escolher = (s: string) => {
    setSlug(s);
    setTransf("nivel");
    setTabela(false);
    window.history.replaceState(null, "", `#/indicadores?serie=${s}`);
  };

  const pontos = useMemo(() => {
    if (!serie.dados || serie.dados.slug !== slug) return [];
    const todos = transformar(
      serie.dados.pontos.map((p) => ({ x: paraData(p.data), y: p.valor })),
      transf,
    );
    if (janela === "tudo" || !todos.length) return todos.filter((p) => p.y !== null);
    const ult = todos[todos.length - 1].x;
    const desde = new Date(ult.getFullYear() - Number(janela), ult.getMonth(), ult.getDate());
    return todos.filter((p) => p.x >= desde && p.y !== null);
  }, [serie.dados, slug, transf, janela]);

  if (lista.erro) return <Erro mensagem={lista.erro} />;
  if (!lista.dados) return <Carregando />;

  const casas = ind?.casas_decimais ?? 2;
  const unidade = transf === "nivel" ? (ind?.unidade ?? "") : "%";
  const fmt = (v: number) => (unidade === "R$/US$" ? `R$ ${num(v, casas)}` : `${num(v, casas)}${unidade.startsWith("%") ? "%" : ""}`);
  const opcoes = ind ? opcoesTransf(ind) : null;
  const valores = pontos.map((p) => p.y as number);

  return (
    <div className="pagina-indicadores">
      <nav className="lista-indicadores" aria-label="Indicadores">
        {lista.dados.map((i) => (
          <button
            key={i.slug}
            type="button"
            className={i.slug === slug ? "ativo" : undefined}
            aria-current={i.slug === slug ? "true" : undefined}
            onClick={() => escolher(i.slug)}
          >
            <span className="chave-cor" style={{ color: corSerie(i.slug) }} />
            <span>
              <span className="li-nome">{i.nome}</span>
              <span className="li-valor">
                {num(i.resumo.valor, i.casas_decimais)} {i.unidade === "índice" ? "" : i.unidade}
              </span>
            </span>
          </button>
        ))}
      </nav>

      {ind && (
        <article className="detalhe-indicador">
          <header>
            <h1>{ind.nome}</h1>
            <p className="secao-descricao">
              {ind.descricao} Fonte: {ind.fonte}. Série{" "}
              <a
                href={`https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarGraficoPorId&hdOidSeriesSelecionadas=${ind.codigo}`}
                target="_blank"
                rel="noreferrer"
              >
                {ind.codigo} no SGS
              </a>
              .
            </p>
          </header>

          <div className="barra-filtros">
            <Segmentado<Janela>
              rotulo="Período"
              valor={janela}
              aoMudar={setJanela}
              opcoes={[
                { valor: "2", rotulo: "2 anos" },
                { valor: "5", rotulo: "5 anos" },
                { valor: "10", rotulo: "10 anos" },
                { valor: "tudo", rotulo: "Histórico" },
              ]}
            />
            {opcoes && <Segmentado<Transf> rotulo="Transformação" valor={transf} aoMudar={setTransf} opcoes={opcoes} />}
          </div>

          <div className={serie.carregando && pontos.length ? "atualizando" : undefined}>
            {serie.erro ? (
              <Erro mensagem={serie.erro} />
            ) : pontos.length ? (
              <GraficoLinhas
                altura={360}
                rotulo={ind.nome}
                formatoY={(v, c) => num(v, c)}
                formatoTooltip={fmt}
                incluirZero={transf !== "nivel" || ind.slug === "selic"}
                series={[
                  {
                    chave: ind.slug,
                    rotulo: ind.nome.split(" (")[0],
                    cor: corSerie(ind.slug),
                    curva: ind.slug === "selic" ? "degrau" : "reta",
                    pontos,
                  },
                ]}
              />
            ) : (
              <Carregando />
            )}
          </div>

          {valores.length > 0 && (
            <dl className="estatisticas">
              <div>
                <dt>Último</dt>
                <dd>{fmt(valores[valores.length - 1])}</dd>
              </div>
              <div>
                <dt>Mínimo no período</dt>
                <dd>{fmt(Math.min(...valores))}</dd>
              </div>
              <div>
                <dt>Máximo no período</dt>
                <dd>{fmt(Math.max(...valores))}</dd>
              </div>
              <div>
                <dt>Observações</dt>
                <dd>{inteiro(valores.length)}</dd>
              </div>
              <div>
                <dt>Último dado</dt>
                <dd>{dataCurta(ind.resumo.data)}</dd>
              </div>
            </dl>
          )}

          <div className="acoes-tabela">
            <button type="button" className="botao-texto" onClick={() => setTabela((t) => !t)} aria-expanded={tabela}>
              {tabela ? "Ocultar tabela" : "Mostrar tabela"}
            </button>
            <button type="button" className="botao-texto" onClick={() => baixarCsv(`${ind.slug}-${transf}`, pontos)}>
              Baixar CSV
            </button>
          </div>
          {tabela && (
            <div className="tabela-rolagem">
              <table className="tabela">
                <thead>
                  <tr>
                    <th scope="col">Data</th>
                    <th scope="col" className="num">
                      Valor
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...pontos].reverse().map((p) => (
                    <tr key={p.x.getTime()}>
                      <td>{diaria ? dataCurta(p.x.toISOString().slice(0, 10)) : mesAno(p.x)}</td>
                      <td className="num">{fmt(p.y as number)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
