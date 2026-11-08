import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, PasswordInput, Stack } from '@mantine/core';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { applyFieldErrors } from '../../lib/apiError';
import { useErrorText } from '../../lib/useErrorText';

const MIN_LENGTH = 12;

interface Values {
  password: string;
  again: string;
}

/**
 * A new password typed twice, for the invitation and the reset pages. The length is checked
 * here; the rest of the policy (common passwords, the account's own name) by the API, whose
 * 422 lands on the field.
 */
export function NewPasswordForm({
  submitLabel,
  onSubmit,
}: {
  submitLabel: string;
  onSubmit: (password: string) => Promise<unknown>;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const schema = z
    .object({
      password: z.string().min(MIN_LENGTH, t('errors.password_too_short')),
      again: z.string(),
    })
    .refine((v) => v.password === v.again, {
      path: ['again'],
      message: t('auth.password.mismatch'),
    });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: '', again: '' },
  });

  const submit = handleSubmit(async ({ password }) => {
    try {
      await onSubmit(password);
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['password'], errorText)) {
        setError('root', { message: t('common.error') });
      }
    }
  });

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="sm">
        {errors.root?.message && (
          <Alert color="red" role="alert">
            {errors.root.message}
          </Alert>
        )}
        <PasswordInput
          label={t('auth.password.new')}
          description={t('auth.password.hint')}
          autoComplete="new-password"
          error={errors.password?.message}
          {...register('password')}
        />
        <PasswordInput
          label={t('auth.password.again')}
          autoComplete="new-password"
          error={errors.again?.message}
          {...register('again')}
        />
        <Button type="submit" loading={isSubmitting}>
          {submitLabel}
        </Button>
      </Stack>
    </form>
  );
}
