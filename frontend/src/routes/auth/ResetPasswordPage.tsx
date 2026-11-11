import { Text } from '@mantine/core';
import { useRouter } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AuthCard } from '../../components/AuthCard';
import { useResetPassword, useTokenInfo } from '../../features/identity/api';
import { NewPasswordForm } from '../../features/identity/NewPasswordForm';
import { InvalidLink } from './InvalidLink';
import { useLinkToken } from './useLinkToken';
import { Loading } from '../../components/QueryStates';

/** A new password from a reset link (plan §5.3). */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const token = useLinkToken();
  const info = useTokenInfo(token);
  const reset = useResetPassword();

  if (token && info.isPending) return <Loading />;
  if (!token || info.isError || info.data?.kind !== 'password_reset') return <InvalidLink />;
  return (
    <AuthCard title={t('auth.reset.title')}>
      <Text>{t('auth.reset.intro', { email: info.data.email })}</Text>
      <NewPasswordForm
        submitLabel={t('auth.reset.submit')}
        onSubmit={async (password) => {
          await reset.mutateAsync({ token, password });
          router.history.push('/login?notice=password-set');
        }}
      />
    </AuthCard>
  );
}
