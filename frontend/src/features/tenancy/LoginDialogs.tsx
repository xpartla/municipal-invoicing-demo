import { zodResolver } from '@hookform/resolvers/zod';
import { Button, Group, Select, Stack, TextInput } from '@mantine/core';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { z } from 'zod';

import { ApiError, applyFieldErrors } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { useInviteLogin } from '../identity/api';
import { useAssignVariableNumber, type Customer } from './api';

interface InviteValues {
  email: string;
  name: string;
  role: 'customer_user' | 'customer_viewer';
}

/** Pozvať prihlásenie: a login for a customer, by mail (plan §5.2, decisions 35–36). */
export function InviteLoginDialog({
  customer,
  onClose,
}: {
  customer: Customer | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const invite = useInviteLogin(customer?.id ?? '');
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteValues>({
    resolver: zodResolver(
      z.object({
        email: z.string().trim().min(1, t('errors.required')),
        name: z.string().trim().min(1, t('errors.required')),
        role: z.enum(['customer_user', 'customer_viewer']),
      }),
    ),
    defaultValues: { email: '', name: '', role: 'customer_user' },
  });
  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit(async (values) => {
    try {
      const done = await invite.mutateAsync(values);
      notify.success(done.new_account ? t('users.invite.sent') : t('users.invite.granted'));
      close();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError('email', { message: t('errors.login_exists') });
      } else if (!applyFieldErrors(error, setError, ['email', 'name', 'role'], errorText)) {
        notify.failure(error);
      }
    }
  });
  return (
    <Dialog
      opened={customer !== null}
      onClose={close}
      title={t('users.invite.title', { customer: customer?.name ?? '' })}
    >
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('users.invite.email')}
            type="email"
            error={errors.email?.message}
            {...register('email')}
          />
          <TextInput
            label={t('users.invite.name')}
            error={errors.name?.message}
            {...register('name')}
          />
          <Controller
            control={control}
            name="role"
            render={({ field }) => (
              <Select
                label={t('users.invite.role')}
                data={[
                  { value: 'customer_user', label: t('roles.customer_user') },
                  { value: 'customer_viewer', label: t('roles.customer_viewer') },
                ]}
                allowDeselect={false}
                value={field.value}
                onChange={(value) => {
                  if (value) field.onChange(value);
                }}
                error={errors.role?.message}
              />
            )}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {t('users.invite.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Dialog>
  );
}

/** Prideliť VS: the customer's variable number (staff and admins, decision 34). */
export function VariableNumberDialog({
  customer,
  onClose,
}: {
  customer: Customer | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const assign = useAssignVariableNumber();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<{ variable_number: string }>({
    values: { variable_number: customer?.variable_number ?? '' },
  });
  const submit = handleSubmit(async ({ variable_number }) => {
    if (!customer) return;
    try {
      await assign.mutateAsync({
        customerId: customer.id,
        body: { variable_number: variable_number.trim() || null },
      });
      notify.success(t('users.vs.saved'));
      onClose();
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['variable_number'], errorText)) notify.failure(error);
    }
  });
  return (
    <Dialog
      opened={customer !== null}
      onClose={onClose}
      title={t('users.vs.title', { customer: customer?.name ?? '' })}
    >
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('users.vs.label')}
            description={t('users.vs.hint')}
            inputMode="numeric"
            error={errors.variable_number?.message}
            {...register('variable_number')}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {t('common.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Dialog>
  );
}
