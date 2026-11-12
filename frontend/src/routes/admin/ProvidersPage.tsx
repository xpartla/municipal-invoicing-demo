import { zodResolver } from '@hookform/resolvers/zod';
import {
  Button,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { z } from 'zod';

import { ConfirmDialog } from '../../components/ConfirmDialog';
import {
  useAddStaff,
  useAssignProvider,
  useCreateProvider,
  useDirectory,
  useProviders,
  useRemoveProvider,
  useRemoveStaff,
  useUnassignProvider,
  type ProviderDetail,
} from '../../features/tenancy/api';
import { applyFieldErrors } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { Loading, LoadFailed } from '../../components/QueryStates';

/**
 * Servisné účty (plan §10.9, admins): providers with their staff and customers; create and
 * remove providers, add and remove staff, assign and unassign customers.
 */
export function ProvidersPage() {
  const { t } = useTranslation();
  const providers = useProviders();
  const directory = useDirectory('all');
  const [creating, setCreating] = useState(false);
  const unassigned = (directory.data ?? [])
    .map((entry) => entry.customer)
    .filter((customer) => customer.provider_id === null);
  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={1}>{t('providers.title')}</Title>
        <Button
          leftSection={<IconPlus size={16} aria-hidden />}
          onClick={() => {
            setCreating(true);
          }}
        >
          {t('providers.create.button')}
        </Button>
      </Group>
      {providers.isPending ? (
        <Loading />
      ) : providers.isError ? (
        <LoadFailed error={providers.error} onRetry={providers.refetch} />
      ) : providers.data.length ? (
        providers.data.map((detail) => (
          <ProviderCard
            key={detail.provider.id}
            detail={detail}
            unassigned={unassigned.map((c) => ({ value: c.id, label: c.name }))}
          />
        ))
      ) : (
        <Text>{t('providers.none')}</Text>
      )}
      <CreateProviderDialog
        opened={creating}
        onClose={() => {
          setCreating(false);
        }}
      />
    </Stack>
  );
}

function ProviderCard({
  detail,
  unassigned,
}: {
  detail: ProviderDetail;
  unassigned: { value: string; label: string }[];
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const { provider, staff, customers } = detail;
  const [adding, setAdding] = useState(false);
  const [asking, setAsking] = useState<
    | { kind: 'staff'; id: string; name: string }
    | { kind: 'customer'; id: string; name: string }
    | { kind: 'provider' }
    | null
  >(null);
  const [toAssign, setToAssign] = useState<string | null>(null);
  const removeStaff = useRemoveStaff();
  const unassign = useUnassignProvider();
  const assign = useAssignProvider();
  const remove = useRemoveProvider();
  const headingId = `provider-${provider.id}`;
  const done = (message: string) => () => {
    notify.success(message);
    setAsking(null);
  };
  return (
    <Paper withBorder p="md" radius="md" component="section" aria-labelledby={headingId}>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start">
          <Stack gap={0}>
            <Title order={2} size="h3" id={headingId}>
              {provider.name}
            </Title>
            {provider.ico && (
              <Text size="sm" c="dimmed">
                {t('profile.customer.ico')} {provider.ico}
              </Text>
            )}
          </Stack>
          <Button
            variant="subtle"
            color="red"
            size="xs"
            onClick={() => {
              setAsking({ kind: 'provider' });
            }}
          >
            {t('providers.remove.button')}
          </Button>
        </Group>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
          <Stack gap="xs">
            <Group justify="space-between">
              <Title order={3} size="h5">
                {t('providers.staff')}
              </Title>
              <Button
                size="xs"
                variant="default"
                onClick={() => {
                  setAdding(true);
                }}
              >
                {t('providers.addStaff.button')}
              </Button>
            </Group>
            {staff.length === 0 ? (
              <Text size="sm" c="dimmed">
                {t('providers.noStaff')}
              </Text>
            ) : (
              <Table>
                <Table.Tbody>
                  {staff.map((member) => (
                    <Table.Tr key={member.user_id}>
                      <Table.Td>
                        <Text size="sm">{member.name}</Text>
                        <Text size="xs" c="dimmed">
                          {member.email}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right">
                        <Button
                          size="xs"
                          variant="subtle"
                          aria-label={`${t('providers.removeStaff.button')}: ${member.name}`}
                          onClick={() => {
                            setAsking({ kind: 'staff', id: member.user_id, name: member.name });
                          }}
                        >
                          {t('providers.removeStaff.button')}
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
          <Stack gap="xs">
            <Title order={3} size="h5">
              {t('providers.customers')}
            </Title>
            {customers.length === 0 ? (
              <Text size="sm" c="dimmed">
                {t('providers.noCustomers')}
              </Text>
            ) : (
              <Table>
                <Table.Tbody>
                  {customers.map((customer) => (
                    <Table.Tr key={customer.id}>
                      <Table.Td>{customer.name}</Table.Td>
                      <Table.Td ta="right">
                        <Button
                          size="xs"
                          variant="subtle"
                          aria-label={`${t('providers.unassign.button')}: ${customer.name}`}
                          onClick={() => {
                            setAsking({ kind: 'customer', id: customer.id, name: customer.name });
                          }}
                        >
                          {t('providers.unassign.button')}
                        </Button>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
            <Group align="flex-end" gap="xs">
              <Select
                label={t('providers.assign.label')}
                placeholder={t('providers.assign.placeholder')}
                data={unassigned}
                value={toAssign}
                onChange={setToAssign}
                searchable
                flex={1}
              />
              <Button
                variant="default"
                disabled={!toAssign}
                loading={assign.isPending}
                onClick={() => {
                  if (!toAssign) return;
                  assign.mutate(
                    { customerId: toAssign, providerId: provider.id },
                    {
                      onSuccess: () => {
                        setToAssign(null);
                        notify.success(t('providers.assign.done'));
                      },
                      onError: notify.failure,
                    },
                  );
                }}
              >
                {t('providers.assign.button')}
              </Button>
            </Group>
          </Stack>
        </SimpleGrid>
      </Stack>
      <AddStaffDialog
        provider={adding ? detail : null}
        onClose={() => {
          setAdding(false);
        }}
      />
      {asking?.kind === 'staff' && (
        <ConfirmDialog
          opened
          title={t('providers.removeStaff.button')}
          message={t('providers.removeStaff.confirm', {
            name: asking.name,
            provider: provider.name,
          })}
          confirmLabel={t('providers.removeStaff.button')}
          danger
          loading={removeStaff.isPending}
          onClose={() => {
            setAsking(null);
          }}
          onConfirm={() => {
            removeStaff.mutate(
              { providerId: provider.id, userId: asking.id },
              { onSuccess: done(t('providers.removeStaff.done')), onError: notify.failure },
            );
          }}
        />
      )}
      {asking?.kind === 'customer' && (
        <ConfirmDialog
          opened
          title={t('providers.unassign.button')}
          message={t('providers.unassign.confirm', {
            customer: asking.name,
            provider: provider.name,
          })}
          confirmLabel={t('providers.unassign.button')}
          danger
          loading={unassign.isPending}
          onClose={() => {
            setAsking(null);
          }}
          onConfirm={() => {
            unassign.mutate(asking.id, {
              onSuccess: done(t('providers.unassign.done')),
              onError: notify.failure,
            });
          }}
        />
      )}
      {asking?.kind === 'provider' && (
        <ConfirmDialog
          opened
          title={t('providers.remove.button')}
          message={t('providers.remove.confirm', { provider: provider.name })}
          confirmLabel={t('providers.remove.button')}
          danger
          loading={remove.isPending}
          onClose={() => {
            setAsking(null);
          }}
          onConfirm={() => {
            remove.mutate(provider.id, {
              onSuccess: done(t('providers.remove.done')),
              onError: notify.failure,
            });
          }}
        />
      )}
    </Paper>
  );
}

interface ProviderValues {
  name: string;
  ico: string;
}

function CreateProviderDialog({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const create = useCreateProvider();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProviderValues>({
    resolver: zodResolver(
      z.object({ name: z.string().trim().min(1, t('errors.required')), ico: z.string().trim() }),
    ),
    defaultValues: { name: '', ico: '' },
  });
  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit(async ({ name, ico }) => {
    try {
      await create.mutateAsync({ name, ico: ico || null });
      notify.success(t('providers.create.done'));
      close();
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['name', 'ico'], errorText)) notify.failure(error);
    }
  });
  return (
    <Dialog opened={opened} onClose={close} title={t('providers.create.title')}>
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('providers.create.name')}
            error={errors.name?.message}
            {...register('name')}
          />
          <TextInput
            label={t('providers.create.ico')}
            error={errors.ico?.message}
            {...register('ico')}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {t('providers.create.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Dialog>
  );
}

interface StaffValues {
  email: string;
  name: string;
}

function AddStaffDialog({
  provider,
  onClose,
}: {
  provider: ProviderDetail | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const add = useAddStaff();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<StaffValues>({
    resolver: zodResolver(
      z.object({
        email: z.string().trim().min(1, t('errors.required')),
        name: z.string().trim().min(1, t('errors.required')),
      }),
    ),
    defaultValues: { email: '', name: '' },
  });
  const close = () => {
    reset();
    onClose();
  };
  const submit = handleSubmit(async (values) => {
    if (!provider) return;
    try {
      await add.mutateAsync({ providerId: provider.provider.id, body: values });
      notify.success(t('providers.addStaff.done'));
      close();
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['email', 'name'], errorText)) notify.failure(error);
    }
  });
  return (
    <Dialog
      opened={provider !== null}
      onClose={close}
      title={t('providers.addStaff.title', { provider: provider?.provider.name ?? '' })}
    >
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('providers.addStaff.email')}
            type="email"
            error={errors.email?.message}
            {...register('email')}
          />
          <TextInput
            label={t('providers.addStaff.name')}
            error={errors.name?.message}
            {...register('name')}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={isSubmitting}>
              {t('providers.addStaff.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Dialog>
  );
}
