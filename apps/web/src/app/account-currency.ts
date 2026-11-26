export type AccountOption = {
  id: string;
  nombre: string;
  moneda?: 'ARS' | 'USD' | 'EUR' | null;
};

export function accountCurrency(accounts: readonly AccountOption[], id: string) {
  return accounts.find(account => account.id === id)?.moneda ?? null;
}

export function compatibleAccounts(accounts: readonly AccountOption[], currency: string) {
  return accounts.filter(account => !account.moneda || account.moneda === currency);
}
