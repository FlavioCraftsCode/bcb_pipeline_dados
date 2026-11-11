// Formatação pt-BR de números e datas.

const cacheFmt = new Map<string, Intl.NumberFormat>();

function fmt(min: number, max: number, sinal = false): Intl.NumberFormat {
  const k = `${min}-${max}-${sinal}`;
  let f = cacheFmt.get(k);
  if (!f) {
    f = new Intl.NumberFormat("pt-BR", {
      minimumFractionDigits: min,
      maximumFractionDigits: max,
      signDisplay: sinal ? "exceptZero" : "auto",
    });
    cacheFmt.set(k, f);
  }
  return f;
}

export function num(v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return fmt(casas, casas).format(v);
}

export function delta(v: number | null | undefined, casas = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return fmt(casas, casas, true).format(v).replace("-", "−");
}

export function inteiro(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return fmt(0, 0).format(v);
}

export function pct(v: number | null | undefined, casas = 0): string {
  if (v === null || v === undefined) return "—";
  return `${fmt(casas, casas).format(v * 100)}%`;
}

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

export function paraData(iso: string): Date {
  // Datas "aaaa-mm-dd" são interpretadas no fuso local (evita voltar um dia em UTC-3).
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [a, m, d] = iso.split("-").map(Number);
    return new Date(a, m - 1, d);
  }
  return new Date(iso);
}

export function dataCurta(iso: string): string {
  const d = paraData(iso);
  return `${d.getDate()} ${MESES[d.getMonth()]} ${d.getFullYear()}`;
}

export function mesAno(iso: string | Date): string {
  const d = typeof iso === "string" ? paraData(iso) : iso;
  return `${MESES[d.getMonth()]} ${d.getFullYear()}`;
}

export function mesAnoLongo(iso: string): string {
  const d = paraData(iso);
  return `${MESES_LONGOS[d.getMonth()]} de ${d.getFullYear()}`;
}

export function dataHora(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${d.getDate()} ${MESES[d.getMonth()]}, ${hh}:${mm}`;
}

export function relativo(iso: string | null, agora = new Date()): string {
  if (!iso) return "—";
  const seg = (agora.getTime() - new Date(iso).getTime()) / 1000;
  if (seg < 90) return "agora há pouco";
  const min = seg / 60;
  if (min < 60) return `há ${Math.round(min)} min`;
  const h = min / 60;
  if (h < 36) return `há ${Math.round(h)} h`;
  return `há ${Math.round(h / 24)} dias`;
}

export function duracao(seg: number | null): string {
  if (seg === null || seg === undefined) return "—";
  if (seg < 60) return `${num(seg, 1)} s`;
  return `${Math.floor(seg / 60)} min ${Math.round(seg % 60)} s`;
}
