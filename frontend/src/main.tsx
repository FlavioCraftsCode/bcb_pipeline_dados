import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MODO_ESTATICO, useDados } from "./api";
import { Status } from "./componentes";
import { relativo } from "./formato";
import { useRota } from "./hooks";
import { Indicadores } from "./paginas/Indicadores";
import { Pipeline } from "./paginas/Pipeline";
import { Previsao } from "./paginas/Previsao";
import { Qualidade } from "./paginas/Qualidade";
import { VisaoGeral } from "./paginas/VisaoGeral";
import "./estilo.css";
import type { StatusExecucao } from "./tipos";

const PAGINAS = [
  { rota: "visao-geral", rotulo: "Visão geral", Componente: VisaoGeral },
  { rota: "indicadores", rotulo: "Indicadores", Componente: Indicadores },
  { rota: "previsao", rotulo: "Previsão", Componente: Previsao },
  { rota: "qualidade", rotulo: "Qualidade de dados", Componente: Qualidade },
  { rota: "pipeline", rotulo: "Pipeline", Componente: Pipeline },
] as const;

interface Saude {
  ultima_execucao: { id: number; status: StatusExecucao; finalizado_em: string | null } | null;
}

function SeloAtualizacao() {
  const saude = useDados<Saude>("saude");
  const ult = saude.dados?.ultima_execucao;
  if (!ult) return null;
  return (
    <a className="selo" href="#/pipeline" title="Ver histórico de execuções">
      <Status status={ult.status} compacto />
      <span>Atualizado {relativo(ult.finalizado_em)}</span>
    </a>
  );
}

function App() {
  const rota = useRota();
  const pagina = PAGINAS.find((p) => p.rota === rota) ?? PAGINAS[0];
  const { Componente } = pagina;
  return (
    <>
      <a className="pular" href="#conteudo">
        Pular para o conteúdo
      </a>
      <header className="topo">
        <div className="topo-interno">
          <a className="marca" href="#/visao-geral">
            <svg width="22" height="22" viewBox="0 0 32 32" aria-hidden="true">
              <rect width="32" height="32" rx="7" fill="currentColor" />
              <path d="M6 22h6v-6h6v-6h8" fill="none" stroke="var(--papel)" strokeWidth="3" />
            </svg>
            Monitor Macro
          </a>
          <nav aria-label="Seções">
            <ul>
              {PAGINAS.map((p) => (
                <li key={p.rota}>
                  <a href={`#/${p.rota}`} aria-current={p.rota === pagina.rota ? "page" : undefined}>
                    {p.rotulo}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <SeloAtualizacao />
        </div>
      </header>
      <main id="conteudo" className="conteudo" data-rota={pagina.rota}>
        <Componente />
      </main>
      <footer className="rodape">
        <p>
          Dados do Sistema Gerenciador de Séries Temporais (SGS) do Banco Central do Brasil, via API pública. Projeto
          independente, sem vínculo com o BCB.
        </p>
        <p>
          <a href="https://github.com/FlavioCraftsCode/bcb_pipeline_dados">Código no GitHub</a>
          {!MODO_ESTATICO && (
            <>
              {" "}
              e <a href="/docs">documentação da API</a>
            </>
          )}
        </p>
      </footer>
    </>
  );
}

createRoot(document.getElementById("raiz") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
