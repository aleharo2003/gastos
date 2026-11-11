import { rateUnits, reference, money } from './money-reference';
describe('Referencia monetaria exacta',()=>{
  const rows=[{moneda:'ARS',dia:'1585.00',mes:'3170.00'},{moneda:'USD',dia:'0.10',mes:'5.00'}];
  it('convierte los agregados sin float y en ambas direcciones',()=>{
    expect(money(reference(rows,'dia','USD',rateUnits('1585'))!)).toBe('1,10');
    expect(money(reference(rows,'mes','ARS',rateUnits('1585'))!)).toBe('11.095,00');
  });
  it('no presenta un parcial cuando falta una conversion',()=>{
    expect(reference(rows,'dia','USD',null)).toBeNull();
    expect(reference([...rows,{moneda:'EUR',dia:'0.01',mes:'0.01'}],'dia','USD',rateUnits('1585'))).toBeNull();
    expect(reference([{moneda:'USD',dia:'0.10',mes:'0.10'}],'dia','USD',null)).toBe(10n);
    expect(reference([],'dia','USD',null)).toBe(0n);
  });
  it('redondea al centavo y conserva importes mayores al entero seguro JS',()=>{
    expect(reference([{moneda:'ARS',dia:'0.01',mes:'0.01'}],'dia','USD',rateUnits('2'))).toBe(1n);
    expect(money(reference([{moneda:'USD',dia:'9007199254740993.01',mes:'0.00'}],'dia','USD',null)!)).toBe('9.007.199.254.740.993,01');
    for(const rate of ['0','-1','1e3','1.234,56','1.00001','NaN'])expect(rateUnits(rate)).toBeNull();
  });
});
