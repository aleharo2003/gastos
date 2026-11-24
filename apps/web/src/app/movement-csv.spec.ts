import { movementCsv } from './movement-csv';

describe('CSV de movimientos', () => {
  it('escapa separadores, comillas y fórmulas', () => {
    const result = movementCsv([{ fecha: '2026-11-24', tipo: 'gasto', descripcion: '=1+1, "nota"',
      moneda: 'ARS', importe: '20.00', origen: 'Caja', destino: null }]);
    expect(result).toContain('"\'=1+1, ""nota"""');
    expect(result).toContain('"ARS","20.00","Caja",""');
  });
});
