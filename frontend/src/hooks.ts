import { type RefObject, useEffect, useRef, useState } from "react";

/** Largura observada de um elemento (para gráficos responsivos). */
export function useLargura<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [largura, setLargura] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new ResizeObserver(([entrada]) => setLargura(Math.floor(entrada.contentRect.width)));
    obs.observe(el);
    setLargura(Math.floor(el.getBoundingClientRect().width));
    return () => obs.disconnect();
  }, []);
  return [ref, largura];
}

/** Rota baseada em hash (#/previsao) — funciona no FastAPI e no GitHub Pages. */
export function useRota(): string {
  const ler = () => window.location.hash.replace(/^#\/?/, "").split("?")[0] || "visao-geral";
  const [rota, setRota] = useState(ler);
  useEffect(() => {
    const f = () => {
      setRota(ler());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return rota;
}
