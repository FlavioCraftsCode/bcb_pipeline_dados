// Cliente de dados. Em modo API consulta o FastAPI; em modo estático lê o
// snapshot JSON publicado junto do site (GitHub Pages). Mesmo contrato nos dois.
import { useEffect, useState } from "react";

declare const __ESTATICO__: boolean;

export const MODO_ESTATICO = typeof __ESTATICO__ !== "undefined" && __ESTATICO__;

function url(rota: string, params: Record<string, string> = {}): string {
  if (MODO_ESTATICO) {
    if (rota.startsWith("series/")) return `data/${rota}-${params.frequencia ?? "mensal"}.json`;
    return `data/${rota}.json`;
  }
  const qs = new URLSearchParams(params).toString();
  return `/api/${rota}${qs ? `?${qs}` : ""}`;
}

const cache = new Map<string, Promise<unknown>>();

export function buscar<T>(rota: string, params: Record<string, string> = {}): Promise<T> {
  const chave = url(rota, params);
  let p = cache.get(chave);
  if (!p) {
    p = fetch(chave).then((r) => {
      if (!r.ok) throw new Error(`Não foi possível carregar ${rota} (HTTP ${r.status}).`);
      return r.json();
    });
    p.catch(() => cache.delete(chave));
    cache.set(chave, p);
  }
  return p as Promise<T>;
}

export interface Estado<T> {
  dados: T | null;
  erro: string | null;
  carregando: boolean;
}

export function useDados<T>(rota: string, params: Record<string, string> = {}): Estado<T> {
  const chave = url(rota, params);
  const [estado, setEstado] = useState<Estado<T>>({ dados: null, erro: null, carregando: true });
  useEffect(() => {
    let vivo = true;
    // Mantém o dado anterior visível durante a troca (sem "piscar" esqueleto).
    setEstado((e) => ({ ...e, carregando: true }));
    buscar<T>(rota, params)
      .then((dados) => vivo && setEstado({ dados, erro: null, carregando: false }))
      .catch((e: Error) => vivo && setEstado({ dados: null, erro: e.message, carregando: false }));
    return () => {
      vivo = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);
  return estado;
}
