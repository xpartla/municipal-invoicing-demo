import type { TFunction } from 'i18next';

import { ApiError } from './apiError';

/**
 * What went wrong, in Slovak: the text of the API's error code when there is one, else
 * whether the server failed (5xx) or could not be reached (the browser's fetch throws a
 * TypeError when the network or the server is down).
 */
export function errorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const code = error.problems[0]?.type ?? error.code;
    if (code) {
      const text = t(`errors.${code}` as 'errors.invalid', { defaultValue: '' });
      if (text) return text;
    }
    return error.status >= 500 ? t('errors.server') : t('common.error');
  }
  if (error instanceof TypeError) return t('errors.network');
  return t('common.error');
}
