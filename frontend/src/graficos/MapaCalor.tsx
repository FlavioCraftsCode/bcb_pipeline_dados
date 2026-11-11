import { useState } from "react";
import { num } from "../formato";
import type { Correlacoes } from "../tipos";

const CURTOS: Record<string, string> = {
  selic: "Selic",
  ipca_12m: "IPCA 12m",
  juro_real: "Juro real",
  dolar_var_12m: "Dólar 12m",
  ibcbr_var_12m: "IBC-Br 12m",
  desemprego: "Desocupação",
  igpm_12m: "IGP-M 12m",
};

// Divergente: azul (negativo) ↔ cinza neutro ↔ vermelho (positivo); a
// intensidade é dada pela opacidade sobre a cor do polo (tokens CSS por tema).

/** Matriz de correlação (triângulo inferior), com valor em cada célula. */
export function MapaCalor({ dados }: { dados: Correlacoes }) {
  const [foco, setFoco] = useState<[number, number] | null>(null);
  const v = dados.variaveis;
  const tam = 52;
  const esquerda = 92;
  const topo = 8;
  const n = v.length;
  const estilo = (r: number | null) => {
    if (r === null) return { fill: "var(--div-meio)" };
    const intensidade = Math.min(1, Math.abs(r));
    return { fill: r >= 0 ? "var(--div-pos)" : "var(--div-neg)", fillOpacity: 0.12 + 0.78 * intensidade };
  };
  return (
    <figure className="mapa-calor">
      <svg
        width={esquerda + n * tam}
        height={topo + n * tam + 70}
        role="img"
        aria-label={`Matriz de correlação de Spearman desde ${dados.desde.slice(0, 4)}`}
        viewBox={`0 0 ${esquerda + n * tam} ${topo + n * tam + 70}`}
        style={{ maxWidth: "100%", height: "auto" }}
      >
        {v.map((lin, i) => (
          <g key={lin}>
            <text x={esquerda - 8} y={topo + i * tam + tam / 2} dy="0.32em" textAnchor="end" className="tick">
              {CURTOS[lin] ?? lin}
            </text>
            {v.slice(0, i + 1).map((col, j) => {
              const r = dados.matriz[i][j];
              const ativo = foco && foco[0] === i && foco[1] === j;
              return (
                <g
                  key={col}
                  transform={`translate(${esquerda + j * tam},${topo + i * tam})`}
                  onPointerEnter={() => setFoco([i, j])}
                  onPointerLeave={() => setFoco(null)}
                >
                  <rect width={tam - 2} height={tam - 2} rx={4} {...estilo(i === j ? null : r)} />
                  {ativo && <rect width={tam - 2} height={tam - 2} rx={4} className="celula-foco" />}
                  {i !== j && (
                    <text x={(tam - 2) / 2} y={(tam - 2) / 2} dy="0.32em" textAnchor="middle" className="valor-celula">
                      {num(r, 2)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        ))}
        {v.map((col, j) => (
          <text
            key={col}
            transform={`translate(${esquerda + j * tam + tam / 2},${topo + n * tam + 8}) rotate(-35)`}
            textAnchor="end"
            className="tick"
          >
            {CURTOS[col] ?? col}
          </text>
        ))}
      </svg>
      <figcaption className="escala-div">
        <span>−1</span>
        <span className="barra-div" aria-hidden="true" />
        <span>+1</span>
        <span className="nota">
          {foco
            ? `${CURTOS[v[foco[0]]]} × ${CURTOS[v[foco[1]]]}: ${num(dados.matriz[foco[0]][foco[1]], 2)}`
            : "Passe o cursor sobre uma célula"}
        </span>
      </figcaption>
    </figure>
  );
}
