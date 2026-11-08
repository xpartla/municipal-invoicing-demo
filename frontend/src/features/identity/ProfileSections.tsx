import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { useRouter } from '@tanstack/react-router';
import { useId } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { z } from 'zod';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import { applyFieldErrors } from '../../lib/apiError';
import { formatDateTime } from '../../lib/format';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import {
  useChangePassword,
  useLogoutEverywhere,
  useRequestEmailChange,
  useSessions,
  useUpdateProfile,
  type Me,
} from './api';

/** The personal sections of Profil (plan §5.5, §10.7). While an admin impersonates, the
 * credential sections are disabled, as the API refuses them too. */

export function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby={id}>
      <Stack gap="sm">
        <Title order={2} size="h3" id={id}>
          {title}
        </Title>
        {children}
      </Stack>
    </Paper>
  );
}

interface PersonalValues {
  name: string;
  notification_email: string;
}

export function PersonalSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const update = useUpdateProfile();
  const schema = z.object({
    name: z.string().trim().min(1, t('errors.required')),
    notification_email: z.string().trim(),
  });
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
    reset,
  } = useForm<PersonalValues>({
    resolver: zodResolver(schema),
    values: { name: me.user.name, notification_email: me.user.notification_email ?? '' },
  });
  const submit = handleSubmit(async (values) => {
    try {
      const saved = await update.mutateAsync(values);
      reset({ name: saved.name, notification_email: saved.notification_email ?? '' });
      notify.success(t('profile.personal.saved'));
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['name', 'notification_email'], errorText)) {
        notify.failure(error);
      }
    }
  });
  return (
    <Section title={t('profile.personal.title')}>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('profile.personal.name')}
            autoComplete="name"
            error={errors.name?.message}
            {...register('name')}
          />
          <TextInput
            label={t('profile.personal.loginEmail')}
            value={me.user.email ?? ''}
            readOnly
          />
          <TextInput
            label={t('profile.personal.notificationEmail')}
            description={t('profile.personal.notificationHint')}
            type="email"
            error={errors.notification_email?.message}
            {...register('notification_email')}
          />
          <Group>
            <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
              {t('common.save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Section>
  );
}

interface EmailValues {
  new_email: string;
  current_password: string;
}

export function EmailSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const request = useRequestEmailChange();
  const blocked = me.impersonation !== null;
  const schema = z.object({
    new_email: z.string().trim().min(1, t('errors.required')),
    current_password: z.string().min(1, t('errors.required')),
  });
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<EmailValues>({
    resolver: zodResolver(schema),
    defaultValues: { new_email: '', current_password: '' },
  });
  const submit = handleSubmit(async (values) => {
    try {
      await request.mutateAsync(values);
      reset();
      notify.success(t('profile.email.sent'));
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['new_email', 'current_password'], errorText)) {
        notify.failure(error);
      }
    }
  });
  return (
    <Section title={t('profile.email.title')}>
      <Text size="sm">{t('profile.email.intro')}</Text>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('profile.email.newEmail')}
            type="email"
            autoComplete="email"
            disabled={blocked}
            error={errors.new_email?.message}
            {...register('new_email')}
          />
          <PasswordInput
            label={t('profile.email.currentPassword')}
            autoComplete="current-password"
            disabled={blocked}
            error={errors.current_password?.message}
            {...register('current_password')}
          />
          <Group>
            <Button type="submit" loading={isSubmitting} disabled={blocked}>
              {t('profile.email.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Section>
  );
}

interface PasswordValues {
  current_password: string;
  new_password: string;
  again: string;
}

export function PasswordSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const change = useChangePassword();
  const blocked = me.impersonation !== null;
  const schema = z
    .object({
      current_password: z.string().min(1, t('errors.required')),
      new_password: z.string().min(12, t('errors.password_too_short')),
      again: z.string(),
    })
    .refine((v) => v.new_password === v.again, {
      path: ['again'],
      message: t('auth.password.mismatch'),
    });
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PasswordValues>({
    resolver: zodResolver(schema),
    defaultValues: { current_password: '', new_password: '', again: '' },
  });
  const submit = handleSubmit(async ({ current_password, new_password }) => {
    try {
      await change.mutateAsync({ current_password, new_password });
      reset();
      notify.success(t('profile.password.changed'));
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['current_password', 'new_password'], errorText)) {
        notify.failure(error);
      }
    }
  });
  return (
    <Section title={t('profile.password.title')}>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <PasswordInput
            label={t('profile.password.current')}
            autoComplete="current-password"
            disabled={blocked}
            error={errors.current_password?.message}
            {...register('current_password')}
          />
          <PasswordInput
            label={t('auth.password.new')}
            description={t('auth.password.hint')}
            autoComplete="new-password"
            disabled={blocked}
            error={errors.new_password?.message}
            {...register('new_password')}
          />
          <PasswordInput
            label={t('auth.password.again')}
            autoComplete="new-password"
            disabled={blocked}
            error={errors.again?.message}
            {...register('again')}
          />
          <Group>
            <Button type="submit" loading={isSubmitting} disabled={blocked}>
              {t('profile.password.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Section>
  );
}

export function SessionsSection({ me }: { me: Me }) {
  const { t } = useTranslation();
  const router = useRouter();
  const notify = useNotify();
  const sessions = useSessions();
  const logoutAll = useLogoutEverywhere();
  const [asking, { open, close }] = useDisclosure(false);
  const blocked = me.impersonation !== null;
  return (
    <Section title={t('profile.sessions.title')}>
      <Text size="sm">{t('profile.sessions.intro')}</Text>
      <ScrollTable label={t('profile.sessions.table')} minWidth={520}>
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('profile.sessions.created')}</Table.Th>
              <Table.Th>{t('profile.sessions.lastSeen')}</Table.Th>
              <Table.Th>{t('profile.sessions.expires')}</Table.Th>
              <Table.Th>{t('profile.sessions.address')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(sessions.data ?? []).map((s) => (
              <Table.Tr key={s.id}>
                <Table.Td>
                  <Group gap="xs">
                    {formatDateTime(s.created_at)}
                    {s.current && <Badge size="sm">{t('profile.sessions.current')}</Badge>}
                  </Group>
                </Table.Td>
                <Table.Td>{formatDateTime(s.last_seen_at)}</Table.Td>
                <Table.Td>{formatDateTime(s.expires_at)}</Table.Td>
                <Table.Td>{s.ip ?? ''}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollTable>
      <Group>
        <Button variant="default" color="red" disabled={blocked} onClick={open}>
          {t('profile.sessions.logoutAll')}
        </Button>
      </Group>
      <ConfirmDialog
        opened={asking}
        title={t('profile.sessions.logoutAll')}
        message={t('profile.sessions.confirmLogoutAll')}
        confirmLabel={t('profile.sessions.logoutAll')}
        danger
        loading={logoutAll.isPending}
        onClose={close}
        onConfirm={() => {
          logoutAll.mutate(undefined, {
            onSuccess: () => {
              router.history.push('/login?notice=logged-out');
            },
            onError: notify.failure,
          });
        }}
      />
    </Section>
  );
}

export function ImpersonationNote({ me }: { me: Me }) {
  const { t } = useTranslation();
  if (!me.impersonation) return null;
  return <Alert color="yellow">{t('profile.impersonating')}</Alert>;
}
