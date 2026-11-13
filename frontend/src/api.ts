// Cliente de dados. Em modo API consulta o FastAPI; em modo estático lê o
// snapshot JSON publicado junto do site (GitHub Pages). Mesmo contrato nos dois.
import { useCallback, useEffect, useState } from "react";

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

const TIMEOUT_MS = 20_000;
const ESPERA_RETENTATIVA_MS = 800;

/** Falhas de rede, timeout e 5xx merecem uma segunda chance; 4xx não. */
class ErroHttp extends Error {
  constructor(
    mensagem: string,
    readonly transitorio: boolean,
  ) {
    super(mensagem);
  }
}

async function buscarUmaVez(endereco: string, rota: string): Promise<unknown> {
  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(endereco, { signal: controle.signal });
    if (!r.ok) throw new ErroHttp(`Não foi possível carregar ${rota} (HTTP ${r.status}).`, r.status >= 500);
    return await r.json();
  } catch (e) {
    if (e instanceof ErroHttp) throw e;
    const motivo = controle.signal.aborted ? "a resposta demorou demais" : "falha de conexão";
    throw new ErroHttp(`Não foi possível carregar ${rota}: ${motivo}.`, true);
  } finally {
    clearTimeout(relogio);
  }
}

async function buscarComRetentativa(endereco: string, rota: string): Promise<unknown> {
  try {
    return await buscarUmaVez(endereco, rota);
  } catch (e) {
    if (!(e instanceof ErroHttp) || !e.transitorio) throw e;
    await new Promise((resolver) => setTimeout(resolver, ESPERA_RETENTATIVA_MS));
    return buscarUmaVez(endereco, rota);
  }
}

export function buscar<T>(rota: string, params: Record<string, string> = {}): Promise<T> {
  const chave = url(rota, params);
  let p = cache.get(chave);
  if (!p) {
    p = buscarComRetentativa(chave, rota);
    p.catch(() => cache.delete(chave));
    cache.set(chave, p);
  }
  return p as Promise<T>;
}

export interface Estado<T> {
  dados: T | null;
  erro: string | null;
  carregando: boolean;
  /** Descarta o cache desta rota e busca de novo (botão "Tentar novamente"). */
  recarregar: () => void;
}

export function useDados<T>(rota: string, params: Record<string, string> = {}): Estado<T> {
  const chave = url(rota, params);
  const [estado, setEstado] = useState<Omit<Estado<T>, "recarregar">>({ dados: null, erro: null, carregando: true });
  const [tentativa, setTentativa] = useState(0);
  const recarregar = useCallback(() => {
    cache.delete(chave);
    setTentativa((n) => n + 1);
  }, [chave]);
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
  }, [chave, tentativa]);
  return { ...estado, recarregar };
}
