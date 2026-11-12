import { cents,rateUnits } from './money-reference';
export type PlanMoney={moneda:'ARS'|'USD';importe:string};
export type PlanConcept=PlanMoney & {id:string;concepto:string;frecuencia:'semana'|'mes'};
export type PlanData={limites:{diario:PlanMoney|null;semanal:PlanMoney|null};conceptos:PlanConcept[]};
export type PlanEnvelope={version:number;datos:PlanData};
export function emptyPlan():PlanData {return {limites:{diario:null,semanal:null},conceptos:[]};}
export function normalizedAmount(value:string):string|null {
  const s=value.trim().replace(',','.');
  if(!/^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,2})?$/.test(s)||!/[1-9]/.test(s))return null;
  const [whole,fraction='']=s.split('.');return whole+'.'+fraction.padEnd(2,'0');
}
export function projected(rows:PlanConcept[],period:'semana'|'mes',currency:'ARS'|'USD',rawRate:string):bigint|null {
  let native=0n,foreign=0n;
  for(const row of rows){
    if(period==='semana'&&row.frecuencia!=='semana')continue;
    const factor=period==='semana'?1n:row.frecuencia==='semana'?13n:3n;
    if(row.moneda===currency)native+=cents(row.importe)*factor;else foreign+=cents(row.importe)*factor;
  }
  const periodDen=period==='semana'?1n:3n;
  if(foreign===0n)return (native+periodDen/2n)/periodDen;
  const rate=rateUnits(rawRate);if(rate===null)return null;
  const conversionDen=currency==='USD'?rate:10000n,conversionNum=currency==='USD'?10000n:rate;
  const denominator=periodDen*conversionDen;
  return (native*conversionDen+foreign*conversionNum+denominator/2n)/denominator;
}
export function progress(spent:bigint,limit:bigint){
  if(limit<=0n)throw new Error('Limite invalido');
  const tenths=spent*1000n/limit;
  return {text:`${tenths/10n},${tenths%10n}%`,width:Number(tenths>1000n?1000n:tenths)/10,
    exceeded:spent>limit,warning:spent*100n>=limit*80n};
}
