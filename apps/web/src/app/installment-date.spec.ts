import { afterEach, describe, expect, it, vi } from 'vitest';
import { installmentLocalDate, watchInstallmentDay } from './installment-date';

describe('Fecha de vencimientos de Argentina', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('cambia de día al comenzar la fecha local', () => {
    expect(installmentLocalDate(new Date('2026-11-18T02:59:59Z'))).toBe('2026-11-17');
    expect(installmentLocalDate(new Date('2026-11-18T03:00:00Z'))).toBe('2026-11-18');
  });

  it('consulta una vez al volver y deja de hacerlo al cerrar la vista', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-18T02:59:30Z'));
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    const refresh = vi.fn().mockReturnValue(true);
    const watch = watchInstallmentDay(refresh);
    try {
      vi.advanceTimersByTime(60_000);
      expect(refresh).not.toHaveBeenCalled();
      hidden.mockReturnValue(false);
      document.dispatchEvent(new Event('visibilitychange'));
      expect(refresh).toHaveBeenCalledWith('2026-11-18');
      vi.advanceTimersByTime(60_000);
      expect(refresh).toHaveBeenCalledTimes(1);
    } finally {
      watch.stop();
    }
    vi.advanceTimersByTime(86_400_000);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
