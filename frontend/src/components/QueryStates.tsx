import { Alert, Button, Center, Loader, Stack, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { errorMessage } from '../lib/errorMessage';

/**
 * The states every screen shows the same way while its data is not there (P2-M8-T02):
 * loading, and a load that failed, with what went wrong and a way to try again. Empty lists
 * keep their own texts, which say what the list would hold.
 */

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <Center py="lg">
      <Loader aria-label={label ?? t('common.loading')} />
    </Center>
  );
}

export function LoadFailed({ error, onRetry }: { error: unknown; onRetry?: () => unknown }) {
  const { t } = useTranslation();
  return (
    <Alert color="red" title={t('states.loadFailed')} icon={<IconAlertTriangle aria-hidden />}>
      <Stack gap="xs" align="flex-start">
        <Text size="sm">{errorMessage(error, t)}</Text>
        {onRetry && (
          <Button size="xs" variant="light" color="red" onClick={() => void onRetry()}>
            {t('states.retry')}
          </Button>
        )}
      </Stack>
    </Alert>
  );
}
