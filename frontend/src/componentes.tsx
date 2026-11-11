import type { ReactNode } from "react";
import type { StatusCheck, StatusExecucao } from "./tipos";

type StatusQualquer = StatusCheck | StatusExecucao | "sucesso" | "quarentena";

const MAPA: Record<string, { classe: string; icone: string; rotulo: string }> = {
  ok: { classe: "bom", icone: "✓", rotulo: "OK" },
  sucesso: { classe: "bom", icone: "✓", rotulo: "Sucesso" },
  alerta: { classe: "atencao", icone: "!", rotulo: "Alerta" },
  parcial: { classe: "atencao", icone: "!", rotulo: "Parcial" },
  quarentena: { classe: "serio", icone: "■", rotulo: "Quarentena" },
  falha: { classe: "critico", icone: "✕", rotulo: "Falha" },
  executando: { classe: "neutro", icone: "…", rotulo: "Executando" },
};

/** Status sempre com ícone + rótulo (nunca só cor). */
export function Status({ status, rotulo, compacto }: { status: StatusQualquer; rotulo?: string; compacto?: boolean }) {
  const m = MAPA[status] ?? MAPA.executando;
  return (
    <span className={`status status-${m.classe}${compacto ? " compacto" : ""}`} title={compacto ? m.rotulo : undefined}>
      <span className="status-icone" aria-hidden="true">
        {m.icone}
      </span>
      {compacto ? <span className="sr">{rotulo ?? m.rotulo}</span> : (rotulo ?? m.rotulo)}
    </span>
  );
}

interface OpcaoSeg<T extends string> {
  valor: T;
  rotulo: string;
}

export function Segmentado<T extends string>({
  opcoes,
  valor,
  aoMudar,
  rotulo,
}: {
  opcoes: OpcaoSeg<T>[];
  valor: T;
  aoMudar: (v: T) => void;
  rotulo: string;
}) {
  return (
    <div className="segmentado" role="radiogroup" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button
          key={o.valor}
          type="button"
          role="radio"
          aria-checked={o.valor === valor}
          className={o.valor === valor ? "ativo" : undefined}
          onClick={() => aoMudar(o.valor)}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}

export function Carregando({ texto = "Carregando dados" }: { texto?: string }) {
  return (
    <div className="carregando" role="status">
      <span className="pulso" aria-hidden="true" />
      {texto}
    </div>
  );
}

export function Erro({ mensagem }: { mensagem: string }) {
  return (
    <div className="erro" role="alert">
      <strong>Não foi possível carregar esta seção.</strong>
      <p>{mensagem}</p>
      <p>Confira se a API está no ar (`uvicorn bcb_api.main:app`) e se a pipeline já rodou ao menos uma vez.</p>
    </div>
  );
}

export function Secao({
  titulo,
  descricao,
  acoes,
  children,
  className,
}: {
  titulo: string;
  descricao?: ReactNode;
  acoes?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`secao${className ? ` ${className}` : ""}`}>
      <header className="secao-cabecalho">
        <div>
          <h2>{titulo}</h2>
          {descricao && <p className="secao-descricao">{descricao}</p>}
        </div>
        {acoes && <div className="secao-acoes">{acoes}</div>}
      </header>
      {children}
    </section>
  );
}
