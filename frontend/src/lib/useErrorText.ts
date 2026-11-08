import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

/** The Slovak message for an API error `type` (`errors.<type>`), else the API's own text. */
export function useErrorText(): (type: string, fallback: string) => string {
  const { t } = useTranslation();
  return useCallback(
    (type: string, fallback: string) =>
      t(`errors.${type}` as 'errors.invalid', { defaultValue: fallback || t('errors.invalid') }),
    [t],
  );
}
