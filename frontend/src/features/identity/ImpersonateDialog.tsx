import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Group, Stack, Text, Textarea } from '@mantine/core';
import { useRouter } from '@tanstack/react-router';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { z } from 'zod';

import { applyFieldErrors } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { useStartImpersonation } from './api';

/** "Prihlásiť sa ako …" with the required reason (plan §5.4, decision 6). */
export function ImpersonateDialog({
  user,
  onClose,
}: {
  user: { id: string; name: string } | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const errorText = useErrorText();
  const notify = useNotify();
  const start = useStartImpersonation();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<{ reason: string }>({
    resolver: zodResolver(z.object({ reason: z.string().trim().min(1, t('errors.required')) })),
    defaultValues: { reason: '' },
  });
  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit(async ({ reason }) => {
    if (!user) return;
    try {
      await start.mutateAsync({ userId: user.id, reason });
      close();
      router.history.push('/');
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['reason'], errorText)) notify.failure(error);
    }
  });
  const name = user?.name ?? '';
  return (
    <Dialog opened={user !== null} onClose={close} title={t('users.impersonate.title', { name })}>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <Text size="sm">{t('users.impersonate.intro')}</Text>
          <Textarea
            label={t('users.impersonate.reason')}
            description={t('users.impersonate.reasonHint')}
            autosize
            minRows={2}
            error={errors.reason?.message}
            {...register('reason')}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" color="yellow" c="dark" loading={isSubmitting}>
              {t('users.impersonate.submit', { name })}
            </Button>
          </Group>
        </Stack>
      </form>
    </Dialog>
  );
}
