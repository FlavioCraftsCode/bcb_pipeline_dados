import { bisector, extent, max, min } from "d3-array";
import { scaleLinear, scaleTime } from "d3-scale";
import { curveLinear, curveMonotoneX, curveStepAfter, line, type CurveFactory } from "d3-shape";
import { useId, useMemo, useState, type KeyboardEvent, type PointerEvent } from "react";
import { mesAno } from "../formato";
import { useLargura } from "../hooks";

export interface PontoXY {
  x: Date;
  y: number | null;
}

export interface SerieGrafico {
  chave: string;
  rotulo: string;
  cor: string;
  pontos: PontoXY[];
  curva?: "degrau" | "suave" | "reta";
  tracejado?: boolean; // reservado para projeções
  rotular?: boolean; // rótulo direto no fim da linha (padrão: sim)
}

export interface FaixaGrafico {
  chave: string;
  rotulo: string;
  cor: string;
  superior: PontoXY[];
  inferior: PontoXY[];
  curvaSuperior?: SerieGrafico["curva"];
  curvaInferior?: SerieGrafico["curva"];
  opacidade?: number;
}

interface Props {
  series: SerieGrafico[];
  faixas?: FaixaGrafico[];
  altura?: number;
  formatoY: (v: number, casas: number) => string;
  formatoTooltip?: (v: number) => string;
  rotulo: string; // descrição acessível
  marcoX?: { data: Date; rotulo: string };
  incluirZero?: boolean;
  rotulosDiretos?: boolean;
  legenda?: boolean;
}

const CURVAS: Record<NonNullable<SerieGrafico["curva"]>, CurveFactory> = {
  degrau: curveStepAfter,
  suave: curveMonotoneX,
  reta: curveLinear,
};

const MARGEM = { topo: 12, direita: 16, base: 28, esquerda: 44 };
const ALTURA_ROTULO = 15;

type Validos = { x: Date; y: number }[];
const validos = (p: PontoXY[]): Validos => p.filter((d): d is { x: Date; y: number } => d.y !== null);
const bisectX = bisector<{ x: Date }, Date>((d) => d.x).center;

/** Espalha rótulos diretos verticalmente para não colidirem. */
function espalhar(ys: number[], minimo: number, alturaMax: number): number[] {
  const ordem = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  for (let k = 1; k < ordem.length; k++) {
    if (ordem[k].y - ordem[k - 1].y < minimo) ordem[k].y = ordem[k - 1].y + minimo;
  }
  const excesso = ordem.length ? ordem[ordem.length - 1].y - alturaMax : 0;
  if (excesso > 0) ordem.forEach((o) => (o.y -= excesso));
  const out = new Array<number>(ys.length);
  ordem.forEach((o) => (out[o.i] = o.y));
  return out;
}

function caminhoFaixa(f: FaixaGrafico, x: (d: Date) => number, y: (v: number) => number): string | null {
  const sup = validos(f.superior);
  const inf = validos(f.inferior);
  if (sup.length < 2 || inf.length < 2) return null;
  const gSup = line<{ x: Date; y: number }>()
    .x((d) => x(d.x))
    .y((d) => y(d.y))
    .curve(CURVAS[f.curvaSuperior ?? "reta"]);
  const gInf = line<{ x: Date; y: number }>()
    .x((d) => x(d.x))
    .y((d) => y(d.y))
    .curve(CURVAS[f.curvaInferior ?? "reta"]);
  const a = gSup(sup);
  const b = gInf([...inf].reverse());
  if (!a || !b) return null;
  return `${a}L${b.slice(1)}Z`;
}

export function GraficoLinhas({
  series,
  faixas = [],
  altura = 320,
  formatoY,
  formatoTooltip,
  rotulo,
  marcoX,
  incluirZero = false,
  rotulosDiretos = true,
  legenda = true,
}: Props) {
  const [ref, largura] = useLargura<HTMLDivElement>();
  const [foco, setFoco] = useState<number | null>(null);
  const idTitulo = useId();
  const fmtTip = formatoTooltip ?? ((v: number) => formatoY(v, 2));

  const larguraRotulos = rotulosDiretos ? 112 : 0;
  const w = Math.max(largura - MARGEM.esquerda - MARGEM.direita - larguraRotulos, 10);
  const h = altura - MARGEM.topo - MARGEM.base;

  const { x, y, eixoX, ticksY, datas } = useMemo(() => {
    const todos = series.flatMap((s) => validos(s.pontos));
    const faixasPts = faixas.flatMap((f) => [...validos(f.superior), ...validos(f.inferior)]);
    const xs = [...todos, ...faixasPts].map((p) => p.x);
    const [x0, x1] = extent(xs) as [Date, Date];
    const ys = [...todos, ...faixasPts].map((p) => p.y);
    let y0 = min(ys) ?? 0;
    let y1 = max(ys) ?? 1;
    if (incluirZero) {
      y0 = Math.min(0, y0);
      y1 = Math.max(0, y1);
    }
    const folga = (y1 - y0 || 1) * 0.06;
    const escalaX = scaleTime()
      .domain([x0 ?? new Date(), x1 ?? new Date()])
      .range([0, w]);
    const escalaY = scaleLinear()
      .domain([y0 - (incluirZero && y0 === 0 ? 0 : folga), y1 + folga])
      .nice(5)
      .range([h, 0]);
    // Datas de referência para o crosshair: a série mais densa.
    const base = [...series].sort((a, b) => b.pontos.length - a.pontos.length)[0];
    return {
      x: escalaX,
      y: escalaY,
      eixoX: escalaX.ticks(Math.max(2, Math.floor(w / 110))),
      ticksY: escalaY.ticks(5),
      datas: base ? validos(base.pontos).map((p) => p.x) : [],
    };
  }, [series, faixas, w, h, incluirZero]);

  const pronto = largura > 0 && datas.length > 1;
  // casas decimais dos ticks seguem o passo do eixo (evita "5, 5, 4, 4")
  const passoY = ticksY.length > 1 ? Math.abs(ticksY[1] - ticksY[0]) : 1;
  const casasY = passoY >= 1 ? 0 : passoY >= 0.1 ? 1 : 2;
  const anosApenas = pronto && x.domain()[1].getFullYear() - x.domain()[0].getFullYear() > 3;

  const ultimos = series.map((s) => {
    const v = validos(s.pontos);
    return v[v.length - 1];
  });
  const posRotulos = espalhar(
    ultimos.map((p) => (p ? y(p.y) : 0)),
    ALTURA_ROTULO * 2 + 2,
    h,
  );

  const dataFoco = foco !== null ? datas[foco] : null;
  const valoresFoco = dataFoco
    ? series.map((s) => {
        const v = validos(s.pontos);
        if (!v.length) return null;
        const i = bisectX(v, dataFoco);
        const p = v[i];
        // só mostra se o ponto mais próximo estiver a menos de ~45 dias
        return Math.abs(p.x.getTime() - dataFoco.getTime()) < 45 * 864e5 ? p : null;
      })
    : [];

  const mover = (e: PointerEvent<SVGRectElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const d = x.invert(e.clientX - rect.left);
    setFoco(bisectX(datas.map((x) => ({ x })), d));
  };

  const teclado = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!datas.length) return;
    const passo = e.shiftKey ? 12 : 1;
    if (e.key === "ArrowRight") setFoco((f) => Math.min(datas.length - 1, (f ?? datas.length - 1) + passo));
    else if (e.key === "ArrowLeft") setFoco((f) => Math.max(0, (f ?? datas.length - 1) - passo));
    else if (e.key === "Escape") setFoco(null);
    else return;
    e.preventDefault();
  };

  const xFoco = dataFoco ? x(dataFoco) : 0;
  const tipEsquerda = xFoco > w * 0.6;

  return (
    <figure className="grafico" ref={ref}>
      {legenda && series.length + faixas.length > 1 && (
        <ul className="legenda">
          {series.map((s) => (
            <li key={s.chave}>
              <span className={`chave-cor${s.tracejado ? " tracejada" : ""}`} style={{ color: s.cor }} />
              {s.rotulo}
            </li>
          ))}
          {faixas.map((f) => (
            <li key={f.chave}>
              <span className="chave-faixa" style={{ background: f.cor }} />
              {f.rotulo}
            </li>
          ))}
        </ul>
      )}
      {pronto && (
        <svg
          width={largura}
          height={altura}
          role="img"
          aria-labelledby={idTitulo}
          tabIndex={0}
          onKeyDown={teclado}
          onBlur={() => setFoco(null)}
        >
          <title id={idTitulo}>{rotulo}. Use as setas para percorrer os valores.</title>
          <g transform={`translate(${MARGEM.esquerda},${MARGEM.topo})`}>
            {ticksY.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={w} className={t === 0 ? "eixo-zero" : "grade"} />
                <text x={-8} dy="0.32em" className="tick" textAnchor="end">
                  {formatoY(t, casasY)}
                </text>
              </g>
            ))}
            <line y1={h} y2={h} x2={w} className="eixo" />
            {eixoX.map((t) => (
              <text key={t.getTime()} x={x(t)} y={h + 18} className="tick" textAnchor="middle">
                {anosApenas ? t.getFullYear() : mesAno(t)}
              </text>
            ))}

            {faixas.map((f) => {
              const d = caminhoFaixa(f, x, y);
              return d ? <path key={f.chave} d={d} fill={f.cor} opacity={f.opacidade ?? 0.16} /> : null;
            })}

            {marcoX && (
              <g transform={`translate(${x(marcoX.data)},0)`}>
                <line y2={h} className="marco" />
                <text y={-2} x={4} className="tick">
                  {marcoX.rotulo}
                </text>
              </g>
            )}

            {series.map((s) => {
              const g = line<{ x: Date; y: number }>()
                .x((d) => x(d.x))
                .y((d) => y(d.y))
                .curve(CURVAS[s.curva ?? "reta"]);
              return (
                <path
                  key={s.chave}
                  d={g(validos(s.pontos)) ?? ""}
                  className="linha"
                  stroke={s.cor}
                  strokeDasharray={s.tracejado ? "5 4" : undefined}
                />
              );
            })}

            {rotulosDiretos &&
              series.map((s, i) => {
                const p = ultimos[i];
                if (!p || s.rotular === false) return null;
                return (
                  <g key={s.chave}>
                    <circle cx={x(p.x)} cy={y(p.y)} r={4} fill={s.cor} className="ponto-final" />
                    <g transform={`translate(${w + 10},${posRotulos[i]})`}>
                      <text className="rotulo-valor" dy="0.1em">
                        {fmtTip(p.y)}
                      </text>
                      <text className="rotulo-serie" dy="1.25em">
                        {s.rotulo.length > 16 ? `${s.rotulo.slice(0, 15)}…` : s.rotulo}
                      </text>
                    </g>
                  </g>
                );
              })}

            {dataFoco && (
              <g className="crosshair" transform={`translate(${xFoco},0)`}>
                <line y2={h} />
                {valoresFoco.map((p, i) =>
                  p ? <circle key={series[i].chave} cy={y(p.y)} r={4.5} fill={series[i].cor} /> : null,
                )}
              </g>
            )}

            <rect
              width={w}
              height={h}
              fill="transparent"
              onPointerMove={mover}
              onPointerDown={mover}
              onPointerLeave={() => setFoco(null)}
            />
          </g>
        </svg>
      )}
      {dataFoco && (
        <div
          className="tooltip"
          role="status"
          style={{
            left: MARGEM.esquerda + xFoco + (tipEsquerda ? -12 : 12),
            top: MARGEM.topo + (legenda ? 34 : 4),
            transform: tipEsquerda ? "translateX(-100%)" : undefined,
          }}
        >
          <div className="tooltip-data">{mesAno(dataFoco)}</div>
          {valoresFoco.map((p, i) =>
            p ? (
              <div key={series[i].chave} className="tooltip-linha">
                <span className="chave-cor" style={{ color: series[i].cor }} />
                <span>{series[i].rotulo}</span>
                <strong>{fmtTip(p.y)}</strong>
              </div>
            ) : null,
          )}
        </div>
      )}
    </figure>
  );
}
