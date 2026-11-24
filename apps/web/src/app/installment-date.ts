const installmentDateFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function installmentLocalDate(now = new Date()): string {
  return installmentDateFormat.format(now);
}

/** Revisa el cambio de fecha al volver a la pestaña y una vez por minuto mientras se usa. */
export function watchInstallmentDay(refresh: (day: string) => boolean) {
  let lastDay = installmentLocalDate();
  const check = () => {
    if (document.hidden) return;
    const day = installmentLocalDate();
    if (day !== lastDay && refresh(day)) lastDay = day;
  };
  const timer = window.setInterval(check, 60_000);
  document.addEventListener('visibilitychange', check);
  return {
    check,
    stop: () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', check);
    },
  };
}
