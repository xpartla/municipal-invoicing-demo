import { Loader, Stack, Text } from '@mantine/core';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AuthCard } from '../../components/AuthCard';
import { useAcceptInvitation, useTokenInfo } from '../../features/identity/api';
import { NewPasswordForm } from '../../features/identity/NewPasswordForm';
import { formatDateTime } from '../../lib/format';
import { InvalidLink } from './InvalidLink';
import { useLinkToken } from './useLinkToken';

/** An invited login sets its password (plan §5.3). */
export function InvitationPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const token = useLinkToken();
  const info = useTokenInfo(token);
  const accept = useAcceptInvitation();

  if (token && info.isPending) return <Loader aria-label={t('common.loading')} />;
  if (!token || info.isError || info.data?.kind !== 'invitation') return <InvalidLink />;
  const { name, email, expires_at } = info.data;
  return (
    <AuthCard title={t('auth.invitation.title')}>
      <Stack gap={4}>
        <Text fw={600}>{t('auth.invitation.greeting', { name })}</Text>
        <Text>{t('auth.invitation.intro', { email })}</Text>
        <Text size="sm" c="dimmed">
          {t('auth.invitation.expires', { date: formatDateTime(expires_at) })}
        </Text>
      </Stack>
      <NewPasswordForm
        submitLabel={t('auth.invitation.submit')}
        onSubmit={async (password) => {
          await accept.mutateAsync({ token, password });
          router.history.push('/login?notice=password-set');
        }}
      />
    </AuthCard>
  );
}
