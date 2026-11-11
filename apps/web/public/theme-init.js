(() => {
  let mode = 'system';
  try {
    const saved = localStorage.getItem('gastos.theme');
    if (saved === 'light' || saved === 'dark') mode = saved;
  } catch { /* The device preference still works without storage. */ }
  document.documentElement.dataset.theme = mode;
})();
