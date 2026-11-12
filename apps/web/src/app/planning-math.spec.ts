import { projected,progress,normalizedAmount,PlanConcept } from './planning-math';
describe('Presupuesto sin mezclar gastos reales',()=>{
  const concept=(importe:string,frecuencia:'semana'|'mes'='semana',moneda:'ARS'|'USD'='ARS'):PlanConcept=>({id:'x',concepto:'Plan',importe:normalizedAmount(importe)!,frecuencia,moneda});
  it('proyecta el ejemplo semanal con 52 semanas y 12 meses',()=>{
    const rows=['30000','30000','100000','90000','20000','200000'].map(v=>concept(v));
    expect(projected(rows,'semana','ARS','')).toBe(47000000n);
    expect(projected(rows,'mes','ARS','')).toBe(203666667n);
    expect(projected([...rows,concept('1000','mes')],'mes','ARS','')).toBe(203766667n);
    expect(projected([...rows,concept('1000','mes')],'semana','ARS','')).toBe(47000000n);
  });
  it('convierte antes de sumar y no oculta una cotización faltante',()=>{
    const rows=[concept('1585','mes'),concept('1','mes','USD')];
    expect(projected(rows,'mes','USD','1585')).toBe(200n);
    expect(projected(rows,'mes','ARS','1585')).toBe(317000n);
    expect(projected(rows,'mes','USD','')).toBeNull();
  });
  it('avisa desde 80% y conserva el exceso aunque la barra llegue a 100%',()=>{
    expect(progress(16000n,20000n).warning).toBe(true);
    expect(progress(25000n,20000n)).toEqual({text:'125,0%',width:100,exceeded:true,warning:true});
    expect(normalizedAmount('200,50')).toBe('200.50');
    expect(normalizedAmount('0')).toBeNull();expect(normalizedAmount('1.000,00')).toBeNull();
  });
});
