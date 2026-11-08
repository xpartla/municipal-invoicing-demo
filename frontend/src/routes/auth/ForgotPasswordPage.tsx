import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Anchor, Button, Stack, Text, TextInput } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { AuthCard } from '../../components/AuthCard';
import { useRequestReset } from '../../features/identity/api';

/** Asks for a reset link. The answer is the same whether or not the address has an account. */
export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const request = useRequestReset();
  const schema = z.object({ email: z.string().trim().min(1, t('errors.required')) });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<{ email: string }>({ resolver: zodResolver(schema), defaultValues: { email: '' } });

  const submit = handleSubmit(async (values) => {
    try {
      await request.mutateAsync(values);
    } catch {
      setError('root', { message: t('common.error') });
    }
  });

  return (
    <AuthCard title={t('auth.forgot.title')}>
      {request.isSuccess ? (
        <Alert color="green" role="status">
          {t('auth.forgot.sent')}
        </Alert>
      ) : (
        <form onSubmit={(event) => void submit(event)} noValidate>
          <Stack gap="sm">
            <Text>{t('auth.forgot.intro')}</Text>
            {errors.root?.message && (
              <Alert color="red" role="alert">
                {errors.root.message}
              </Alert>
            )}
            <TextInput
              label={t('auth.forgot.email')}
              type="email"
              autoComplete="username"
              error={errors.email?.message}
              {...register('email')}
            />
            <Button type="submit" loading={isSubmitting}>
              {t('auth.forgot.submit')}
            </Button>
          </Stack>
        </form>
      )}
      <Anchor component={Link} to="/login" size="sm">
        {t('auth.forgot.back')}
      </Anchor>
    </AuthCard>
  );
}
