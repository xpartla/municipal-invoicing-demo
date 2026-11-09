import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../../lib/apiError';
import { useErrorText } from '../../lib/useErrorText';

/** The Slovak text of a failed call: its first problem's or its code's (`errors.<code>`),
 * else the API's own words. */
export function useProblemText(): (error: unknown) => string {
  const { t } = useTranslation();
  const errorText = useErrorText();
  return useCallback(
    (error: unknown) => {
      if (!(error instanceof ApiError)) return t('common.error');
      const problem = error.problems[0];
      const detail = (error.body as { detail?: unknown } | null)?.detail;
      const fallback = problem?.msg ?? (typeof detail === 'string' ? detail : '');
      return errorText(problem?.type ?? error.code ?? 'invalid', fallback);
    },
    [t, errorText],
  );
}
