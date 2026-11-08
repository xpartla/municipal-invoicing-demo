import 'i18next';

import type sk from './sk/translation.json';

// Typed keys: t('shell.nav.home') is checked against the Slovak resources.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof sk };
  }
}
