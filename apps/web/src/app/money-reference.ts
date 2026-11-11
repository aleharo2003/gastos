export type CurrencyTotal = {moneda:string;dia:string;mes:string};
export function rateUnits(value:string): bigint | null {
  const normalized=value.trim().replace(',', '.');
  if(!/^(?:0|[1-9][0-9]{0,7})(?:\.[0-9]{1,4})?$/.test(normalized)) return null;
  const [whole,fraction='']=normalized.split('.');
  const rate=BigInt(whole)*10000n+BigInt(fraction.padEnd(4,'0'));
  return rate>0n ? rate : null;
}
export function cents(value:string):bigint {
  if(!/^(?:0|[1-9][0-9]{0,30})\.[0-9]{2}$/.test(value)) throw new Error('Importe invalido');
  return BigInt(value.replace('.',''));
}
export function money(value:bigint):string {
  return (value/100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g,'.')+','+(value%100n).toString().padStart(2,'0');
}
export function reference(rows:CurrencyTotal[],period:'dia'|'mes',currency:'ARS'|'USD',rate:bigint|null):bigint|null {
  let native=0n,other=0n;
  for(const row of rows) {
    const amount=cents(row[period]);
    if(row.moneda===currency) native+=amount;
    else if(['ARS','USD'].includes(row.moneda)) other+=amount;
    else if(amount!==0n) return null;
  }
  if(other===0n) return native;
  if(rate===null) return null;
  const numerator=currency==='USD' ? other*10000n : other*rate;
  const denominator=currency==='USD' ? rate : 10000n;
  return native+(numerator+denominator/2n)/denominator;
}
