import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, Group, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { ApiError, applyFieldErrors } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import type { Me } from '../identity/api';
import { inCustomer } from '../identity/capabilities';
import { Section } from '../identity/ProfileSections';
import {
  useAssignVariableNumber,
  useCustomer,
  useUpdateContact,
  useUpdateIdentity,
  type Customer,
} from './api';
import { Loading, LoadFailed } from '../../components/QueryStates';

/**
 * The customer's fields on Profil (plan §5.5, decision 50): the user edits the address and
 * the bank account; staff and admins also the name, IČO and DIČ, and assign the variable
 * number. Without a permission a field is shown read-only.
 */
export function CustomerProfile({ me, initial }: { me: Me; initial: string | undefined }) {
  const { t } = useTranslation();
  const [customerId, setCustomerId] = useState(initial ?? me.customers[0]?.id);
  const customer = useCustomer(customerId);
  if (customerId === undefined) return null;
  return (
    <Section title={t('profile.customer.title')}>
      {me.customers.length > 1 && (
        <Select
          label={t('profile.customer.choose')}
          data={me.customers.map((c) => ({ value: c.id, label: c.name }))}
          value={customerId}
          allowDeselect={false}
          searchable
          onChange={(value) => {
            if (value) setCustomerId(value);
          }}
        />
      )}
      {customer.isPending && <Loading />}
      {customer.isError && <LoadFailed error={customer.error} onRetry={customer.refetch} />}
      {customer.data && <CustomerForms me={me} customer={customer.data} key={customer.data.id} />}
    </Section>
  );
}

function CustomerForms({ me, customer }: { me: Me; customer: Customer }) {
  const { t } = useTranslation();
  const can = (permission: Parameters<typeof inCustomer>[2]) =>
    inCustomer(me, customer.id, permission);
  const editsContact = can('customer.edit_contact');
  return (
    <Stack gap="lg">
      {!editsContact && <Alert color="gray">{t('profile.customer.readOnly')}</Alert>}
      <IdentityForm customer={customer} editable={can('customer.edit_identity')} />
      <ContactForm customer={customer} editable={editsContact} />
      <VariableNumberForm customer={customer} editable={can('customer.assign_variable_number')} />
    </Stack>
  );
}

interface IdentityValues {
  name: string;
  ico: string;
  dic: string;
}

function IdentityForm({ customer, editable }: { customer: Customer; editable: boolean }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const update = useUpdateIdentity();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<IdentityValues>({
    resolver: zodResolver(
      z.object({
        name: z.string().trim().min(1, t('errors.required')),
        ico: z.string().trim().min(1, t('errors.required')),
        dic: z.string().trim(),
      }),
    ),
    values: { name: customer.name, ico: customer.ico, dic: customer.dic ?? '' },
  });
  const submit = handleSubmit(async ({ name, ico, dic }) => {
    try {
      await update.mutateAsync({ customerId: customer.id, body: { name, ico, dic: dic || null } });
      notify.success(t('profile.customer.saved'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError('ico', { message: t('errors.ico_taken') });
      } else if (!applyFieldErrors(error, setError, ['name', 'ico', 'dic'], errorText)) {
        notify.failure(error);
      }
    }
  });
  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="sm">
        <TextInput
          label={t('profile.customer.name')}
          readOnly={!editable}
          error={errors.name?.message}
          {...register('name')}
        />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            label={t('profile.customer.ico')}
            readOnly={!editable}
            error={errors.ico?.message}
            {...register('ico')}
          />
          <TextInput
            label={t('profile.customer.dic')}
            readOnly={!editable}
            error={errors.dic?.message}
            {...register('dic')}
          />
        </SimpleGrid>
        {editable ? (
          <Group>
            <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
              {t('profile.customer.saveIdentity')}
            </Button>
          </Group>
        ) : (
          <Text size="sm" c="dimmed">
            {t('profile.customer.identityHint')}
          </Text>
        )}
      </Stack>
    </form>
  );
}

interface ContactValues {
  address: { street: string; city: string; postal_code: string };
  iban: string;
}

const CONTACT_FIELDS = ['address.street', 'address.city', 'address.postal_code', 'iban'] as const;

function ContactForm({ customer, editable }: { customer: Customer; editable: boolean }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const update = useUpdateContact();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<ContactValues>({
    values: {
      address: {
        street: customer.address?.street ?? '',
        city: customer.address?.city ?? '',
        postal_code: customer.address?.postal_code ?? '',
      },
      iban: customer.iban ?? '',
    },
  });
  const submit = handleSubmit(async ({ address, iban }) => {
    const hasAddress = Boolean(address.street || address.city || address.postal_code);
    try {
      await update.mutateAsync({
        customerId: customer.id,
        body: { address: hasAddress ? { ...address, country: 'SK' } : null, iban: iban || null },
      });
      notify.success(t('profile.customer.saved'));
    } catch (error) {
      if (!applyFieldErrors(error, setError, CONTACT_FIELDS, errorText)) notify.failure(error);
    }
  });
  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="sm">
        <TextInput
          label={t('profile.customer.street')}
          readOnly={!editable}
          error={errors.address?.street?.message}
          {...register('address.street')}
        />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            label={t('profile.customer.city')}
            readOnly={!editable}
            error={errors.address?.city?.message}
            {...register('address.city')}
          />
          <TextInput
            label={t('profile.customer.postalCode')}
            readOnly={!editable}
            error={errors.address?.postal_code?.message}
            {...register('address.postal_code')}
          />
        </SimpleGrid>
        <TextInput
          label={t('profile.customer.iban')}
          readOnly={!editable}
          error={errors.iban?.message}
          {...register('iban')}
        />
        {editable && (
          <Group>
            <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
              {t('profile.customer.saveContact')}
            </Button>
          </Group>
        )}
      </Stack>
    </form>
  );
}

function VariableNumberForm({ customer, editable }: { customer: Customer; editable: boolean }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const assign = useAssignVariableNumber();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<{ variable_number: string }>({
    values: { variable_number: customer.variable_number ?? '' },
  });
  const submit = handleSubmit(async ({ variable_number }) => {
    try {
      await assign.mutateAsync({
        customerId: customer.id,
        body: { variable_number: variable_number || null },
      });
      notify.success(t('users.vs.saved'));
    } catch (error) {
      if (!applyFieldErrors(error, setError, ['variable_number'], errorText)) notify.failure(error);
    }
  });
  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Group align="flex-end" gap="sm">
        <TextInput
          label={t('profile.customer.variableNumber')}
          description={editable ? t('users.vs.hint') : t('profile.customer.variableNumberHint')}
          readOnly={!editable}
          error={errors.variable_number?.message}
          {...register('variable_number')}
        />
        {editable && (
          <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
            {t('common.save')}
          </Button>
        )}
      </Group>
    </form>
  );
}
