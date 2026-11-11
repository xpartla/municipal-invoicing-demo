import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Anchor, Button, PasswordInput, Stack, TextInput } from '@mantine/core';
import { Link, useRouter, useSearch } from '@tanstack/react-router';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { AuthCard } from '../../components/AuthCard';
import { useLogin } from '../../features/identity/api';
import { landingPath, safeNext } from '../../features/identity/capabilities';
import { ApiError } from '../../lib/apiError';

interface Values {
  email: string;
  password: string;
}

const NOTICES = {
  'password-set': 'auth.login.passwordSet',
  'email-changed': 'auth.login.emailChanged',
  'logged-out': 'auth.login.loggedOut',
  'session-expired': 'auth.login.sessionExpired',
} as const;

export function LoginPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const search = useSearch({ from: '/login' });
  const login = useLogin();
  const schema = z.object({
    email: z.string().trim().min(1, t('errors.required')),
    password: z.string().min(1, t('errors.required')),
  });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  const submit = handleSubmit(async (values) => {
    try {
      const me = await login.mutateAsync(values);
      router.history.push(safeNext(search.next) ?? landingPath(me) ?? '/');
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        const minutes = Math.max(1, Math.ceil((error.retryAfter ?? 60) / 60));
        setError('root', { message: t('auth.login.throttled', { minutes }) });
      } else if (error instanceof ApiError && error.status === 401) {
        setError('root', { message: t('auth.login.failed') });
      } else {
        setError('root', { message: t('common.error') });
      }
    }
  });

  const notice = search.notice && search.notice in NOTICES ? NOTICES[search.notice] : undefined;
  return (
    <AuthCard title={t('auth.login.title')}>
      {notice && (
        <Alert color={search.notice === 'session-expired' ? 'yellow' : 'green'}>{t(notice)}</Alert>
      )}
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          {errors.root?.message && (
            <Alert color="red" role="alert">
              {errors.root.message}
            </Alert>
          )}
          <TextInput
            label={t('auth.login.email')}
            type="email"
            autoComplete="username"
            error={errors.email?.message}
            {...register('email')}
          />
          <PasswordInput
            label={t('auth.login.password')}
            autoComplete="current-password"
            error={errors.password?.message}
            {...register('password')}
          />
          <Button type="submit" loading={isSubmitting}>
            {t('auth.login.submit')}
          </Button>
          <Anchor component={Link} to="/forgot-password" size="sm">
            {t('auth.login.forgot')}
          </Anchor>
        </Stack>
      </form>
    </AuthCard>
  );
}
