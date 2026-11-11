import { Alert, Button, Text } from '@mantine/core';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AuthCard } from '../../components/AuthCard';
import { useConfirmEmailChange, useTokenInfo } from '../../features/identity/api';
import { InvalidLink } from './InvalidLink';
import { useLinkToken } from './useLinkToken';
import { Loading } from '../../components/QueryStates';

/** Confirms a new login email. A button, not an automatic request, so a mail scanner that
 * opens the link does not confirm it. */
export function ConfirmEmailPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const token = useLinkToken();
  const info = useTokenInfo(token);
  const confirm = useConfirmEmailChange();

  if (token && info.isPending) return <Loading />;
  if (!token || info.isError || info.data?.kind !== 'email_change') return <InvalidLink />;
  return (
    <AuthCard title={t('auth.confirmEmail.title')}>
      <Text>{t('auth.confirmEmail.intro', { email: info.data.email })}</Text>
      {confirm.isError && (
        <Alert color="red" role="alert">
          {t('common.error')}
        </Alert>
      )}
      <Button
        loading={confirm.isPending}
        onClick={() => {
          void confirm.mutateAsync({ token }).then(() => {
            router.history.push('/login?notice=email-changed');
          });
        }}
      >
        {t('auth.confirmEmail.submit')}
      </Button>
    </AuthCard>
  );
}
