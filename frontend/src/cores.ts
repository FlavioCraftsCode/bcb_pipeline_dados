// Cor segue a entidade, nunca a posição: cada indicador tem um slot fixo da
// paleta categórica (validada para daltonismo nos modos claro e escuro).
// Os valores vivem em CSS (variáveis --s1..--s8); aqui só o mapeamento.

export const SLOT: Record<string, number> = {
  selic: 1,
  ipca: 2,
  ipca_12m: 2,
  dolar: 3,
  dolar_var_12m: 3,
  ibcbr: 4,
  ibcbr_var_12m: 4,
  desemprego: 5,
  juro_real: 6,
  igpm: 7,
  igpm_12m: 7,
};

export function corSerie(chave: string): string {
  return `var(--s${SLOT[chave] ?? 1})`;
}
