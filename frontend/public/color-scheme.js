// Applies the remembered or the system colour scheme before the app renders, so the page
// does not flash light in dark mode. The key is Mantine's localStorageColorSchemeManager's.
(function () {
  try {
    var stored = window.localStorage.getItem('mantine-color-scheme-value');
    var scheme =
      stored === 'light' || stored === 'dark'
        ? stored
        : window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light';
    document.documentElement.setAttribute('data-mantine-color-scheme', scheme);
  } catch {
    // Storage may be blocked; Mantine falls back to the system scheme.
  }
})();
