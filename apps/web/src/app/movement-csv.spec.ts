import { movementCsv } from './movement-csv';

describe('CSV de movimientos', () => {
  it('escapa separadores, comillas y fórmulas', () => {
    const result = movementCsv([{ fecha: '2026-11-24', tipo: 'gasto', descripcion: '=1+1, "nota"',
      moneda: 'ARS', importe: '20.00', origen: 'Caja', destino: null }]);
    expect(result).toContain('"\'=1+1, ""nota"""');
    expect(result).toContain('"ARS","20.00","Caja",""');
  });
  it('incluye categorías de gastos e ingresos y deja vacías las categorías ausentes', () => {
    const row = { fecha: '2026-11-24', descripcion: 'Detalle', moneda: 'ARS', importe: '20.00',
      origen: 'Caja', destino: null, categoria: 'ocio' };
    const label = (id: string | null, kind: string) => kind === 'ingreso' && id === 'sueldo' ? 'Sueldo' : 'Ocio';
    expect(movementCsv([{ ...row, tipo: 'gasto' }, { ...row, tipo: 'ingreso', categoria: 'sueldo' },
      { ...row, tipo: 'ingreso', categoria: null }], label).split('\r\n').slice(1, 4))
      .toEqual(['"2026-11-24","gasto","Detalle","ARS","20.00","Caja","","Ocio","",""',
        '"2026-11-24","ingreso","Detalle","ARS","20.00","Caja","","Sueldo","",""',
        '"2026-11-24","ingreso","Detalle","ARS","20.00","Caja","","","",""']);
  });

  it('exporta las dos monedas de un cambio en una sola fila', () => {
    const csv = movementCsv([{ fecha: '2026-11-24', tipo: 'cambio', descripcion: 'Casa de cambio',
      moneda: 'ARS', importe: '160000.00', origen: 'Pesos', destino: 'Dólares',
      moneda_destino: 'USD', importe_destino: '100.00' }]);
    expect(csv).toContain('Moneda recibida,Importe recibido');
    expect(csv).toContain('"cambio","Casa de cambio","ARS","160000.00","Pesos","Dólares","","USD","100.00"');
  });
});
