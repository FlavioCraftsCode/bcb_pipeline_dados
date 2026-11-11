import { extent } from "d3-array";
import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import type { Ponto } from "../tipos";

interface Props {
  pontos: Ponto[];
  cor: string;
  largura?: number;
  altura?: number;
}

/** Minigráfico de tendência (36 meses), sem eixos. */
export function Faisca({ pontos, cor, largura = 120, altura = 36 }: Props) {
  const v = pontos.filter((p): p is { data: string; valor: number } => p.valor !== null);
  if (v.length < 2) return null;
  const [y0, y1] = extent(v, (p) => p.valor) as [number, number];
  const x = scaleLinear()
    .domain([0, v.length - 1])
    .range([2, largura - 5]);
  const y = scaleLinear()
    .domain([y0, y1 === y0 ? y0 + 1 : y1])
    .range([altura - 4, 4]);
  const d = line<{ valor: number }>()
    .x((_, i) => x(i))
    .y((p) => y(p.valor))(v);
  const ult = v[v.length - 1];
  return (
    <svg width={largura} height={altura} aria-hidden="true" className="faisca">
      <path d={d ?? ""} stroke={cor} />
      <circle cx={x(v.length - 1)} cy={y(ult.valor)} r={3} fill={cor} />
    </svg>
  );
}
