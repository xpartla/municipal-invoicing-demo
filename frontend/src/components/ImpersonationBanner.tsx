import { Alert, Button, Group, Text } from '@mantine/core';
import { IconUserShield } from '@tabler/icons-react';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { useEndImpersonation, type Me } from '../features/identity/api';

/** The amber banner while an admin acts as someone (plan §5.4): "Ste prihlásený ako … ·
 * Ukončiť". */
export function ImpersonationBanner({ me }: { me: Me }) {
  const { t } = useTranslation();
  const router = useRouter();
  const end = useEndImpersonation();
  if (!me.impersonation) return null;
  return (
    <Alert
      color="yellow"
      variant="light"
      mb="md"
      icon={<IconUserShield aria-hidden />}
      title={t('shell.impersonation.banner', { name: me.user.name })}
    >
      <Group justify="space-between" gap="sm">
        <Text size="sm">
          {t('shell.impersonation.reason', { reason: me.impersonation.reason })}
        </Text>
        <Button
          size="xs"
          color="yellow"
          variant="filled"
          c="dark"
          loading={end.isPending}
          onClick={() => {
            void end.mutateAsync().then(() => {
              router.history.push('/users');
            });
          }}
        >
          {t('shell.impersonation.end')}
        </Button>
      </Group>
    </Alert>
  );
}
