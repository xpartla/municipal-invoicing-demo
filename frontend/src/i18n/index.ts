import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import sk from './sk/translation.json';

/**
 * Slovak only for now, built for translation (plan §2, decision 42). Keys are
 * `feature.area.key`; components get text through `useTranslation()`, never as literals.
 */
export const resources = { sk: { translation: sk } } as const;

void i18n.use(initReactI18next).init({
  resources,
  lng: 'sk',
  fallbackLng: 'sk',
  interpolation: { escapeValue: false }, // React escapes already
  returnNull: false,
});

export default i18n;
