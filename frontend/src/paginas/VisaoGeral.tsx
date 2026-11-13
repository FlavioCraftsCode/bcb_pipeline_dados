import { useMemo, useState } from "react";
import { useDados } from "../api";
import { Carregando, Erro, Secao, Segmentado } from "../componentes";
import { corSerie } from "../cores";
import { dataCurta, delta, mesAno, mesAnoLongo, num, paraData } from "../formato";
import { Faisca } from "../graficos/Faisca";
import { GraficoLinhas, type PontoXY } from "../graficos/GraficoLinhas";
import { MapaCalor } from "../graficos/MapaCalor";
import type { Correlacoes, Destaques, Indicador, MetaInflacao, Painel, Previsao } from "../tipos";

type Janela = "5" | "10" | "tudo";

const ORDEM_FAIXA = ["selic", "ipca_12m", "ipca", "dolar", "ibcbr", "desemprego"];

function serieDoPainel(p: Painel, chave: string, desde: Date): PontoXY[] {
  return p.linhas
    .map((l) => ({ x: paraData(l.data), y: (l[chave] as number | null) ?? null }))
    .filter((d) => d.x >= desde);
}

function Manchete({ painel }: { painel: Painel }) {
  const jr = painel.ultimo.juro_real;
  const selic = painel.ultimo.selic;
  const ipca = painel.ultimo.ipca_12m;
  if (!jr || !selic || !ipca) return null;
  return (
    <div className="manchete">
      <h1>
        O juro real está em {num(jr.valor, 1)}% ao ano: a Selic é de {num(selic.valor, 2)}% e a inflação acumulada em 12
        meses, de {num(ipca.valor, 2)}%.
      </h1>
      <p className="manchete-nota">
        Juro real ex-post pela equação de Fisher, com a meta Selic e o IPCA de {mesAnoLongo(ipca.data)}.
      </p>
    </div>
  );
}

function variacao(ind: Indicador): { texto: string; sentido: "sobe" | "desce" | "estavel" } {
  const { valor, valor_12m_atras } = ind.resumo;
  if (valor_12m_atras === null) return { texto: "—", sentido: "estavel" };
  // Taxas (% ) comparam em pontos percentuais; níveis (R$, índice) em variação %.
  const ehTaxa = ind.unidade.startsWith("%");
  const d = ehTaxa ? valor - valor_12m_atras : (valor / valor_12m_atras - 1) * 100;
  const sentido = Math.abs(d) < 0.005 ? "estavel" : d > 0 ? "sobe" : "desce";
  return { texto: `${delta(d, ehTaxa ? 2 : 1)}${ehTaxa ? " p.p." : "%"} em 12 meses`, sentido };
}

function Instrumentos({ indicadores }: { indicadores: Indicador[] }) {
  const lista = ORDEM_FAIXA.map((s) => indicadores.find((i) => i.slug === s)).filter(
    (i): i is Indicador => i !== undefined,
  );
  return (
    <ul className="instrumentos" aria-label="Últimos valores dos indicadores">
      {lista.map((ind) => {
        const v = variacao(ind);
        const nome = ind.slug === "ipca_12m" ? "IPCA em 12 meses" : ind.slug === "ipca" ? "IPCA no mês" : ind.nome;
        return (
          <li key={ind.slug}>
            <a href={`#/indicadores?serie=${ind.slug}`} className="instrumento">
              <span className="instrumento-nome">{nome.replace(/ \(.*\)$/, "")}</span>
              <span className="instrumento-valor">
                {num(ind.resumo.valor, ind.casas_decimais)}
                <span className="unidade">{ind.unidade === "índice" ? "" : ` ${ind.unidade}`}</span>
              </span>
              <span className={`instrumento-delta ${v.sentido}`}>
                <span aria-hidden="true">{v.sentido === "sobe" ? "▲" : v.sentido === "desce" ? "▼" : "■"} </span>
                {v.texto}
              </span>
              <Faisca pontos={ind.faisca} cor={corSerie(ind.slug)} />
              <span className="instrumento-data">
                {ind.periodicidade === "mensal" ? mesAno(ind.resumo.data) : `em ${ind.resumo.data.split("-").reverse().join("/")}`}
              </span>
            </a>
          </li>
        );
      })}
    </ul>
  );
}

function PrevisaoResumo({ previsao }: { previsao: Previsao }) {
  if (!previsao.disponivel || !previsao.previsao || !previsao.historico) return <p>Previsão ainda não gerada.</p>;
  const hist = previsao.historico.slice(-24);
  const prev = previsao.previsao;
  const ultimoHist = hist[hist.length - 1];
  const fim = prev[prev.length - 1];
  const ponte = { x: paraData(ultimoHist.data), y: ultimoHist.ipca_12m };
  return (
    <>
      <p className="destaque-numero">
        {num(fim.previsto_12m, 1)}%
        <span>
          esperado para o IPCA em 12 meses até {mesAno(fim.data)} (intervalo de 80%: {num(fim.li_12m, 1)}% a{" "}
          {num(fim.ls_12m, 1)}%)
        </span>
      </p>
      <GraficoLinhas
        altura={210}
        rotulo="IPCA acumulado em 12 meses, realizado e previsto"
        formatoY={(v, c) => num(v, c)}
        formatoTooltip={(v) => `${num(v, 2)}%`}
        rotulosDiretos={false}
        series={[
          {
            chave: "real",
            rotulo: "Realizado",
            cor: corSerie("ipca"),
            curva: "suave",
            pontos: hist.map((h) => ({ x: paraData(h.data), y: h.ipca_12m })),
          },
          {
            chave: "prev",
            rotulo: "Previsto",
            cor: corSerie("ipca"),
            curva: "suave",
            tracejado: true,
            pontos: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: p.previsto_12m }))],
          },
        ]}
        faixas={[
          {
            chave: "ic",
            rotulo: "Intervalo de 80%",
            cor: corSerie("ipca"),
            superior: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: p.ls_12m }))],
            inferior: [ponte, ...prev.map((p) => ({ x: paraData(p.data), y: p.li_12m }))],
            opacidade: 0.14,
          },
        ]}
      />
      <a className="link-secao" href="#/previsao">
        Ver metodologia e comparação de modelos
      </a>
    </>
  );
}

const SITUACAO_META: Record<MetaInflacao["situacao"], string> = {
  dentro: "dentro da banda de tolerância",
  acima: "acima do teto da banda de tolerância",
  abaixo: "abaixo do piso da banda de tolerância",
};

function TermometroMeta({ meta }: { meta: MetaInflacao }) {
  const max = Math.max(7, Math.ceil(meta.ipca_12m + 1));
  const min = Math.min(0, Math.floor(meta.ipca_12m - 1));
  const pct = (v: number) => Math.min(100, Math.max(0, ((v - min) / (max - min)) * 100));
  const fora = meta.meses_consecutivos_fora;
  return (
    <>
      <p className="destaque-numero">
        {num(meta.ipca_12m, 2)}%
        <span>
          IPCA em 12 meses ({mesAnoLongo(meta.data)}), {SITUACAO_META[meta.situacao]}: {delta(meta.desvio_pp, 2)} p.p.
          em relação à meta de {num(meta.meta, 1)}%.
        </span>
      </p>
      <div
        className="meta-trilho"
        role="img"
        aria-label={`IPCA em 12 meses de ${num(meta.ipca_12m, 2)}%. Meta de ${num(meta.meta, 1)}% com banda de ${num(meta.piso, 1)}% a ${num(meta.teto, 1)}%.`}
      >
        <span className="meta-banda" style={{ left: `${pct(meta.piso)}%`, width: `${pct(meta.teto) - pct(meta.piso)}%` }} />
        <span className="meta-alvo" style={{ left: `${pct(meta.meta)}%` }} />
        <span className={`meta-marcador ${meta.situacao}`} style={{ left: `${pct(meta.ipca_12m)}%` }} />
      </div>
      <ul className="meta-escala" aria-hidden="true">
        <li style={{ left: `${pct(meta.piso)}%` }}>{num(meta.piso, 1)}%</li>
        <li style={{ left: `${pct(meta.meta)}%` }}>meta {num(meta.meta, 1)}%</li>
        <li style={{ left: `${pct(meta.teto)}%` }}>{num(meta.teto, 1)}%</li>
      </ul>
      <p className="nota-pequena">
        {fora > 0
          ? `Fora da banda há ${fora} ${fora === 1 ? "mês consecutivo" : "meses consecutivos"}; o descumprimento formal da meta exige ${meta.meses_para_descumprimento}.`
          : "Dentro da banda no último mês."}
      </p>
    </>
  );
}

function DecisoesCopom({ selic }: { selic: NonNullable<Destaques["selic"]> }) {
  const { decisoes } = selic;
  return (
    <>
      <p className="destaque-numero">
        {num(selic.atual, 2)}%
        <span>
          meta Selic vigente
          {decisoes.length > 0
            ? `, sem mudança há ${selic.dias_desde_ultima_mudanca} ${selic.dias_desde_ultima_mudanca === 1 ? "dia" : "dias"}`
            : ""}
          .
        </span>
      </p>
      {decisoes.length > 0 ? (
        <ol className="decisoes" aria-label="Últimas mudanças da meta Selic">
          {decisoes.slice(0, 6).map((d) => (
            <li key={d.data}>
              <time dateTime={d.data}>{dataCurta(d.data)}</time>
              <span className={`decisao-delta ${d.variacao_pp > 0 ? "sobe" : "desce"}`}>
                <span aria-hidden="true">{d.variacao_pp > 0 ? "▲" : "▼"} </span>
                {delta(d.variacao_pp, 2)} p.p.
              </span>
              <span className="decisao-faixa">
                {num(d.de, 2)}% → {num(d.para, 2)}%
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="nota-pequena">Nenhuma mudança registrada no histórico carregado.</p>
      )}
      <p className="nota-pequena">Datas de início de vigência da nova meta, conforme a série 432 do SGS.</p>
    </>
  );
}

export function VisaoGeral() {
  const painel = useDados<Painel>("painel");
  const indicadores = useDados<Indicador[]>("indicadores");
  const previsao = useDados<Previsao>("previsao");
  const correl = useDados<Correlacoes>("correlacoes");
  // Opcional: snapshots antigos podem não ter /destaques; nesse caso a seção some em silêncio.
  const destaques = useDados<Destaques>("destaques");
  const [janela, setJanela] = useState<Janela>("10");

  const hero = useMemo(() => {
    if (!painel.dados) return null;
    const p = painel.dados;
    const ultimo = paraData(p.linhas[p.linhas.length - 1].data);
    const desde =
      janela === "tudo" ? new Date(1999, 0, 1) : new Date(ultimo.getFullYear() - Number(janela), ultimo.getMonth(), 1);
    const selic = serieDoPainel(p, "selic", desde);
    const ipca = serieDoPainel(p, "ipca_12m", desde);
    // a faixa só existe onde as duas séries existem
    const datasIpca = new Set(ipca.filter((d) => d.y !== null).map((d) => d.x.getTime()));
    const selicComum = selic.filter((d) => datasIpca.has(d.x.getTime()));
    const datasSelic = new Set(selicComum.map((d) => d.x.getTime()));
    return { selic, ipca, selicComum, ipcaComum: ipca.filter((d) => datasSelic.has(d.x.getTime())) };
  }, [painel.dados, janela]);

  const blocos = destaques.dados;

  if (painel.erro) return <Erro mensagem={painel.erro} aoTentar={painel.recarregar} />;
  if (!painel.dados || !hero) return <Carregando />;

  return (
    <>
      <Manchete painel={painel.dados} />
      <section className="hero" aria-label="Selic e inflação">
        <div className="hero-controles">
          <p className="hero-legenda-texto">
            Meta Selic definida pelo Copom e IPCA acumulado em 12 meses. A área sombreada é a distância entre as duas, o
            juro real.
          </p>
          <Segmentado<Janela>
            rotulo="Período do gráfico"
            valor={janela}
            aoMudar={setJanela}
            opcoes={[
              { valor: "5", rotulo: "5 anos" },
              { valor: "10", rotulo: "10 anos" },
              { valor: "tudo", rotulo: "Desde 1999" },
            ]}
          />
        </div>
        <GraficoLinhas
          altura={380}
          rotulo="Meta Selic e IPCA acumulado em 12 meses"
          formatoY={(v, c) => `${num(v, c)}%`}
          formatoTooltip={(v) => `${num(v, 2)}%`}
          incluirZero
          series={[
            { chave: "selic", rotulo: "Meta Selic", cor: corSerie("selic"), curva: "degrau", pontos: hero.selic },
            { chave: "ipca_12m", rotulo: "IPCA 12 meses", cor: corSerie("ipca"), curva: "suave", pontos: hero.ipca },
          ]}
          faixas={[
            {
              chave: "juro",
              rotulo: "Juro real",
              cor: corSerie("selic"),
              superior: hero.selicComum,
              inferior: hero.ipcaComum,
              curvaSuperior: "degrau",
              curvaInferior: "suave",
              opacidade: 0.13,
            },
          ]}
        />
      </section>

      {indicadores.dados && <Instrumentos indicadores={indicadores.dados} />}

      {blocos && (blocos.meta_inflacao || blocos.selic) && (
        <div className="duas-colunas igual">
          {blocos.meta_inflacao && (
            <Secao titulo="A inflação frente à meta" descricao="Meta contínua de 3% com tolerância de 1,5 ponto percentual.">
              <TermometroMeta meta={blocos.meta_inflacao} />
            </Secao>
          )}
          {blocos.selic && (
            <Secao titulo="Decisões do Copom" descricao="Mudanças recentes da meta Selic.">
              <DecisoesCopom selic={blocos.selic} />
            </Secao>
          )}
        </div>
      )}

      <div className="duas-colunas">
        <Secao titulo="Para onde vai a inflação" descricao="Previsão do modelo com melhor desempenho no backtest.">
          {previsao.dados ? <PrevisaoResumo previsao={previsao.dados} /> : <Carregando />}
        </Secao>
        <Secao
          titulo="Como os indicadores andam juntos"
          descricao={`Correlação de Spearman entre séries mensais${correl.dados ? `, desde ${correl.dados.desde.slice(0, 4)}` : ""}.`}
        >
          {correl.dados ? <MapaCalor dados={correl.dados} /> : <Carregando />}
        </Secao>
      </div>
    </>
  );
}
