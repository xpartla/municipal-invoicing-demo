import { notifications } from '@mantine/notifications';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from './errorMessage';

/**
 * Toasts for the outcome of an action. A failure says what the API's error code means, or
 * that the server failed or could not be reached (`errorMessage`). The close button is
 * named, which Mantine's is not by default (axe's button-name).
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
      notifications.show({
        message: errorMessage(error, t),
        color: 'red',
        autoClose: 8000,
        closeButtonProps: { 'aria-label': t('common.close') },
      });
    },
    [t],
  );
  return { success, failure };
}
