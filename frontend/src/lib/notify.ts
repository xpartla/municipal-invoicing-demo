import { notifications } from '@mantine/notifications';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from './apiError';

/**
 * Toasts for the outcome of an action. A failure says what the API's error code means. The
 * close button is named, which Mantine's is not by default (axe's button-name).
 */
export function useNotify() {
  const { t } = useTranslation();
  const success = useCallback(
    (message: string) => {
      notifications.show({
        message,
        color: 'green',
        autoClose: 4000,
        closeButtonProps: { 'aria-label': t('common.close') },
      });
    },
    [t],
  );
  const failure = useCallback(
    (error: unknown) => {
      let message = t('common.error');
      if (error instanceof ApiError) {
        const problem = error.problems[0];
        const code = problem?.type ?? error.code;
        if (code) message = t(`errors.${code}` as 'errors.invalid', { defaultValue: message });
      }
      notifications.show({
        message,
        color: 'red',
        autoClose: 8000,
        closeButtonProps: { 'aria-label': t('common.close') },
      });
    },
    [t],
  );
  return { success, failure };
}
