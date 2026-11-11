import { useState } from "react";
import { useDados } from "../api";
import { Carregando, Erro, Secao, Segmentado } from "../componentes";
import { corSerie } from "../cores";
import { dataHora, mesAno, mesAnoLongo, num, paraData, pct } from "../formato";
import { GraficoLinhas } from "../graficos/GraficoLinhas";
import type { Previsao as TPrevisao } from "../tipos";

type Visao = "acum" | "mensal";

const NOMES: Record<string, string> = {
  ingenuo_sazonal: "Ingênuo sazonal",
  media_sazonal: "Média sazonal",
  ridge_lags: "Ridge com defasagens",
  gbm_lags: "Gradient boosting",
};

export function Previsao() {
  const { dados, erro } = useDados<TPrevisao>("previsao");
  const [visao, setVisao] = useState<Visao>("acum");
  if (erro) return <Erro mensagem={erro} />;
  if (!dados) return <Carregando />;
  if (!dados.disponivel || !dados.previsao || !dados.metricas || !dados.historico)
    return <p className="vazio">Ainda não há previsão. Rode `python -m bcb_pipeline prever` depois da primeira carga.</p>;

  const prev = dados.previsao;
  const hist = dados.historico;
  const escolhido = dados.metricas.find((m) => m.escolhido) ?? dados.metricas[0];
  const ingenuo = dados.metricas.find((m) => m.modelo === "ingenuo_sazonal");
  const acum = visao === "acum";
  const ult = hist[hist.length - 1];
  const ponte = { x: paraData(ult.data), y: acum ? ult.ipca_12m : ult.ipca };
  const fim = prev[prev.length - 1];

  return (
    <>
      <header className="cabecalho-pagina">
        <h1>Previsão do IPCA para os próximos 12 meses</h1>
        <p className="secao-descricao">
          Quatro modelos competem num backtest walk-forward: cada um treina só com o passado e prevê 12 meses à frente,
          repetido em {escolhido.origens} datas. O de menor erro médio vence e gera a previsão abaixo. Atualizado em{" "}
          {dataHora(dados.gerado_em ?? null)}, com dados até {mesAnoLongo(dados.data_base ?? ult.data)}.
        </p>
      </header>

      <div className="faixa-kpis">
        <div>
          <span className="kpi-rotulo">IPCA em 12 meses até {mesAno(fim.data)}</span>
          <span className="kpi-valor">{num(fim.previsto_12m, 1)}%</span>
          <span className="kpi-nota">
            entre {num(fim.li_12m, 1)}% e {num(fim.ls_12m, 1)}% com 80% de confiança
          </span>
        </div>
        <div>
          <span className="kpi-rotulo">Modelo escolhido</span>
          <span className="kpi-valor kpi-texto">{NOMES[escolhido.modelo] ?? escolhido.modelo}</span>
          <span className="kpi-nota">{escolhido.descricao}</span>
        </div>
        <div>
          <span className="kpi-rotulo">Erro médio mensal</span>
          <span className="kpi-valor">{num(escolhido.mae, 2)} p.p.</span>
          <span className="kpi-nota">
            {escolhido.skill !== null && ingenuo
              ? `${pct(escolhido.skill)} menor que o ingênuo sazonal (${num(ingenuo.mae, 2)} p.p.)`
              : "—"}
          </span>
        </div>
        <div>
          <span className="kpi-rotulo">Cobertura do intervalo</span>
          <span className="kpi-valor">{pct(escolhido.cobertura)}</span>
          <span className="kpi-nota">dos valores realizados caíram dentro do intervalo de 80% no backtest</span>
        </div>
      </div>

      <Secao
        titulo={acum ? "IPCA acumulado em 12 meses" : "IPCA no mês"}
        acoes={
          <Segmentado<Visao>
            rotulo="Visão da previsão"
            valor={visao}
            aoMudar={setVisao}
            opcoes={[
              { valor: "acum", rotulo: "Acumulado 12 meses" },
              { valor: "mensal", rotulo: "Variação mensal" },
            ]}
          />
        }
      >
        <GraficoLinhas
          altura={360}
          rotulo="IPCA realizado e previsto com intervalo de 80%"
          formatoY={(v, c) => num(v, c)}
          formatoTooltip={(v) => `${num(v, 2)}%`}
          incluirZero={!acum}
          marcoX={{ data: ponte.x, rotulo: "Último dado" }}
          series={[
            {
              chave: "real",
              rotulo: "Realizado",
              cor: corSerie("ipca"),
              curva: acum ? "suave" : "reta",
              rotular: false,
              pontos: hist.map((h) => ({ x: paraData(h.data), y: acum ? h.ipca_12m : h.ipca })),
            },
            {
              chave: "prev",
              rotulo: "Previsto",
              cor: corSerie("ipca"),
              curva: acum ? "suave" : "reta",
              tracejado: true,
              pontos: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: acum ? p.previsto_12m : p.previsto }))],
            },
          ]}
          faixas={[
            {
              chave: "ic",
              rotulo: "Intervalo de 80%",
              cor: corSerie("ipca"),
              superior: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: acum ? p.ls_12m : p.ls }))],
              inferior: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: acum ? p.li_12m : p.li }))],
              opacidade: 0.15,
            },
          ]}
        />
      </Secao>

      <Secao
        titulo="Comparação de modelos no backtest"
        descricao="Erro absoluto médio (MAE) e raiz do erro quadrático médio (RMSE) em pontos percentuais, nos horizontes de 1 a 12 meses. Ganho = redução do MAE em relação ao ingênuo sazonal."
      >
        <div className="tabela-rolagem">
          <table className="tabela">
            <thead>
              <tr>
                <th scope="col">Modelo</th>
                <th scope="col" className="num">
                  MAE mensal
                </th>
                <th scope="col" className="num">
                  RMSE mensal
                </th>
                <th scope="col" className="num">
                  MAE do acumulado 12m
                </th>
                <th scope="col" className="num">
                  Ganho vs. ingênuo
                </th>
              </tr>
            </thead>
            <tbody>
              {dados.metricas.map((m) => (
                <tr key={m.modelo} className={m.escolhido ? "linha-destaque" : undefined}>
                  <td>
                    <strong>{NOMES[m.modelo] ?? m.modelo}</strong>
                    {m.escolhido && <span className="etiqueta">em uso</span>}
                    <span className="sub">{m.descricao}</span>
                  </td>
                  <td className="num">{num(m.mae, 3)}</td>
                  <td className="num">{num(m.rmse, 3)}</td>
                  <td className="num">{num(m.mae_12m, 2)}</td>
                  <td className="num">{m.modelo === "ingenuo_sazonal" ? "base" : pct(m.skill)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Secao>

      <Secao titulo="Como ler esta previsão">
        <ul className="lista-texto">
          <li>
            O intervalo vem dos erros que o próprio modelo cometeu no backtest, por horizonte. Não supõe distribuição
            normal, e por isso se abre conforme o prazo aumenta.
          </li>
          <li>
            Os modelos usam só o histórico do IPCA. Choques de câmbio, preços administrados e mudanças de política
            monetária não estão no modelo. É uma referência estatística, não uma projeção oficial.
          </li>
          <li>O treino começa em 2004 para evitar o regime de inflação muito alta dos anos 1990.</li>
        </ul>
      </Secao>
    </>
  );
}
