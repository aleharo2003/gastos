import { movementCsv } from './movement-csv';

describe('CSV de movimientos', () => {
  it('escapa separadores, comillas y fórmulas', () => {
    const result = movementCsv([{ fecha: '2026-11-24', tipo: 'gasto', descripcion: '=1+1, "nota"',
      moneda: 'ARS', importe: '20.00', origen: 'Caja', destino: null }]);
    expect(result).toContain('"\'=1+1, ""nota"""');
    expect(result).toContain('"ARS","20.00","Caja",""');
  });
  it('incluye la categoría de un gasto y deja vacía la de un ingreso', () => {
    const row = { fecha: '2026-11-24', descripcion: 'Detalle', moneda: 'ARS', importe: '20.00',
      origen: 'Caja', destino: null, categoria: 'ocio' };
    expect(movementCsv([{ ...row, tipo: 'gasto' }, { ...row, tipo: 'ingreso' }]).split('\r\n').slice(1, 3))
      .toEqual(['"2026-11-24","gasto","Detalle","ARS","20.00","Caja","","Ocio"',
        '"2026-11-24","ingreso","Detalle","ARS","20.00","Caja","",""']);
  });
});
