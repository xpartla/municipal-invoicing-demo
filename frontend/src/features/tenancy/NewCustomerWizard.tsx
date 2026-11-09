import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  Group,
  Loader,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Stepper,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { Controller, useForm, useWatch, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { ButtonLink } from '../../components/RouterLinks';
import { ApiError, applyFieldErrors } from '../../lib/apiError';
import { useErrorText } from '../../lib/useErrorText';
import type { Me } from '../identity/api';
import { onPlatform } from '../identity/capabilities';
import {
  useCreateCustomer,
  useCustomerJob,
  useDirectory,
  useProviders,
  type CustomerCreated,
} from './api';

const NONE = 'none';

interface Values {
  mode: 'new' | 'copy';
  sourceId: string;
  year: string;
  providerId: string;
  name: string;
  ico: string;
  dic: string;
  street: string;
  city: string;
  postalCode: string;
  iban: string;
  variableNumber: string;
  parameters: boolean;
  codeLists: boolean;
  conventions: boolean;
  templates: boolean;
  supplierMemory: boolean;
  invite: boolean;
  email: string;
  loginName: string;
  role: 'customer_user' | 'customer_viewer';
}

type Step = 0 | 1 | 2 | 3;

const STEP_FIELDS: Record<Step, Path<Values>[]> = {
  0: ['mode', 'sourceId', 'year'],
  1: ['providerId', 'name', 'ico', 'dic', 'street', 'city', 'postalCode', 'iban', 'variableNumber'],
  2: [],
  3: ['email', 'loginName', 'role'],
};

/** The API's field paths onto the form's. */
const API_FIELDS: Record<string, Path<Values>> = {
  name: 'name',
  ico: 'ico',
  dic: 'dic',
  'address.street': 'street',
  'address.city': 'city',
  'address.postal_code': 'postalCode',
  iban: 'iban',
};

/** Nový klient (plan §9.3): new or as a copy of one of the caller's customers; the identity;
 * what to copy; optionally the first login. A copy runs as a job, which the last screen
 * follows. Staff create in their provider; admins choose a provider or none. */
export function NewCustomerWizard({ me }: { me: Me }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const admin = onPlatform(me, 'customers.create');
  const staffProviders = me.providers.filter((p) => p.permissions.includes('customers.create'));
  const providers = useProviders(admin);
  const directory = useDirectory(
    admin ? 'all' : staffProviders[0] ? { providerId: staffProviders[0].id } : undefined,
  );
  const create = useCreateCustomer();
  const [step, setStep] = useState<Step>(0);
  const [created, setCreated] = useState<CustomerCreated | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const thisYear = new Date().getFullYear();

  const required = z.string().trim().min(1, t('errors.required'));
  const schema = z
    .object({
      mode: z.enum(['new', 'copy']),
      sourceId: z.string(),
      year: z.string(),
      providerId: z.string(),
      name: required,
      ico: required,
      dic: z.string().trim(),
      street: z.string().trim(),
      city: z.string().trim(),
      postalCode: z.string().trim(),
      iban: z.string().trim(),
      variableNumber: z
        .string()
        .trim()
        .regex(/^\d{0,10}$/, t('errors.variable_number')),
      parameters: z.boolean(),
      codeLists: z.boolean(),
      conventions: z.boolean(),
      templates: z.boolean(),
      supplierMemory: z.boolean(),
      invite: z.boolean(),
      email: z.string().trim(),
      loginName: z.string().trim(),
      role: z.enum(['customer_user', 'customer_viewer']),
    })
    .superRefine((values, context) => {
      if (values.mode === 'copy' && !values.sourceId) {
        context.addIssue({ code: 'custom', path: ['sourceId'], message: t('errors.required') });
      }
      const address = [values.street, values.city, values.postalCode];
      if (address.some(Boolean) && !address.every(Boolean)) {
        for (const [key, value] of [
          ['street', values.street],
          ['city', values.city],
          ['postalCode', values.postalCode],
        ] as const) {
          if (!value)
            context.addIssue({
              code: 'custom',
              path: [key],
              message: t('newCustomer.addressWhole'),
            });
        }
      }
      if (values.invite) {
        if (!values.email)
          context.addIssue({ code: 'custom', path: ['email'], message: t('errors.required') });
        if (!values.loginName)
          context.addIssue({ code: 'custom', path: ['loginName'], message: t('errors.required') });
      }
    });

  const {
    register,
    control,
    handleSubmit,
    trigger,
    setError,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      mode: 'new',
      sourceId: '',
      year: String(thisYear),
      providerId: admin ? NONE : (staffProviders[0]?.id ?? ''),
      name: '',
      ico: '',
      dic: '',
      street: '',
      city: '',
      postalCode: '',
      iban: '',
      variableNumber: '',
      parameters: true,
      codeLists: true,
      conventions: true,
      templates: true,
      supplierMemory: false,
      invite: false,
      email: '',
      loginName: '',
      role: 'customer_user',
    },
  });
  const mode = useWatch({ control, name: 'mode' });
  const invite = useWatch({ control, name: 'invite' });
  const steps: Step[] = mode === 'copy' ? [0, 1, 2, 3] : [0, 1, 3];
  const position = steps.indexOf(step);
  const last = position === steps.length - 1;

  const next = async () => {
    if (await trigger(STEP_FIELDS[step])) setStep(steps[position + 1] ?? step);
  };

  const submit = handleSubmit(async (values) => {
    setProblem(null);
    const providerId = values.providerId === NONE ? null : values.providerId;
    try {
      const done = await create.mutateAsync({
        identity: {
          name: values.name,
          ico: values.ico,
          dic: values.dic || null,
          address: values.street
            ? {
                street: values.street,
                city: values.city,
                postal_code: values.postalCode,
                country: 'SK',
              }
            : null,
          iban: values.iban || null,
        },
        target:
          admin || providerId === null
            ? { providerId, asAdmin: true }
            : { providerId, asAdmin: false },
        copy:
          values.mode === 'copy'
            ? {
                sourceId: values.sourceId,
                options: {
                  year: Number(values.year),
                  parameters: values.parameters,
                  code_lists: values.codeLists,
                  conventions: values.conventions,
                  templates: values.templates,
                  supplier_memory: values.supplierMemory,
                },
              }
            : null,
        variableNumber: values.variableNumber || null,
        invite: values.invite
          ? { email: values.email, name: values.loginName, role: values.role }
          : null,
      });
      setCreated(done);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError('ico', { message: t('errors.ico_taken') });
        setStep(1);
        return;
      }
      if (error instanceof ApiError && error.status === 422) {
        let mapped = false;
        for (const problem of error.problems) {
          const loc = problem.loc[0] === 'body' ? problem.loc.slice(1) : problem.loc;
          const field = API_FIELDS[loc.join('.')];
          if (field) {
            setError(field, { message: errorText(problem.type, problem.msg) });
            mapped = true;
          }
        }
        if (mapped) {
          setStep(1);
          return;
        }
        if (applyFieldErrors(error, setError, [], errorText)) return;
      }
      setProblem(t('common.error'));
    }
  });

  if (created) return <Created created={created} />;

  const sources = (directory.data ?? []).map((entry) => ({
    value: entry.customer.id,
    label: `${entry.customer.name} (${entry.customer.ico})`,
  }));
  const providerOptions = admin
    ? [
        { value: NONE, label: t('newCustomer.noProvider') },
        ...(providers.data ?? []).map((p) => ({ value: p.provider.id, label: p.provider.name })),
      ]
    : staffProviders.map((p) => ({ value: p.id, label: p.name }));

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (last) void submit(event);
        else void next();
      }}
    >
      <Stack gap="md">
        <Stepper active={position} size="sm" allowNextStepsSelect={false}>
          {steps.map((s) => (
            <Stepper.Step key={s} label={t(`newCustomer.steps.${String(s) as '0'}`)} />
          ))}
        </Stepper>

        {step === 0 && (
          <Stack gap="sm" maw={560}>
            <Controller
              control={control}
              name="mode"
              render={({ field }) => (
                <Radio.Group
                  label={t('newCustomer.mode')}
                  value={field.value}
                  onChange={(value) => {
                    field.onChange(value);
                  }}
                >
                  <Stack gap="xs" mt="xs">
                    <Radio value="new" label={t('newCustomer.modes.new')} />
                    <Radio value="copy" label={t('newCustomer.modes.copy')} />
                  </Stack>
                </Radio.Group>
              )}
            />
            {mode === 'copy' && (
              <>
                <Controller
                  control={control}
                  name="sourceId"
                  render={({ field }) => (
                    <Select
                      label={t('newCustomer.source')}
                      data={sources}
                      searchable
                      value={field.value || null}
                      onChange={(value) => {
                        field.onChange(value ?? '');
                      }}
                      error={errors.sourceId?.message}
                    />
                  )}
                />
                <Controller
                  control={control}
                  name="year"
                  render={({ field }) => (
                    <Select
                      label={t('newCustomer.year')}
                      description={t('newCustomer.yearHint')}
                      data={[thisYear + 1, thisYear, thisYear - 1].map((y) => ({
                        value: String(y),
                        label: String(y),
                      }))}
                      value={field.value}
                      allowDeselect={false}
                      onChange={(value) => {
                        if (value) field.onChange(value);
                      }}
                      w={160}
                    />
                  )}
                />
              </>
            )}
          </Stack>
        )}

        {step === 1 && (
          <Stack gap="sm" maw={720}>
            {providerOptions.length > 1 && (
              <Controller
                control={control}
                name="providerId"
                render={({ field }) => (
                  <Select
                    label={t('newCustomer.provider')}
                    data={providerOptions}
                    value={field.value}
                    allowDeselect={false}
                    onChange={(value) => {
                      if (value) field.onChange(value);
                    }}
                  />
                )}
              />
            )}
            <TextInput
              label={t('newCustomer.name')}
              required
              error={errors.name?.message}
              {...register('name')}
            />
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <TextInput
                label={t('newCustomer.ico')}
                required
                error={errors.ico?.message}
                {...register('ico')}
              />
              <TextInput
                label={t('newCustomer.dic')}
                error={errors.dic?.message}
                {...register('dic')}
              />
              <TextInput
                label={t('newCustomer.variableNumber')}
                description={t('newCustomer.variableNumberHint')}
                error={errors.variableNumber?.message}
                {...register('variableNumber')}
              />
            </SimpleGrid>
            <SimpleGrid cols={{ base: 1, sm: 3 }}>
              <TextInput
                label={t('newCustomer.street')}
                error={errors.street?.message}
                {...register('street')}
              />
              <TextInput
                label={t('newCustomer.city')}
                error={errors.city?.message}
                {...register('city')}
              />
              <TextInput
                label={t('newCustomer.postalCode')}
                error={errors.postalCode?.message}
                {...register('postalCode')}
              />
            </SimpleGrid>
            <TextInput
              label={t('newCustomer.iban')}
              error={errors.iban?.message}
              {...register('iban')}
            />
          </Stack>
        )}

        {step === 2 && (
          <Stack gap="xs" maw={720}>
            <Text>{t('newCustomer.copyIntro')}</Text>
            {(
              ['parameters', 'codeLists', 'conventions', 'templates', 'supplierMemory'] as const
            ).map((name) => (
              <Checkbox
                key={name}
                label={t(`newCustomer.copy.${name}`)}
                description={t(`newCustomer.copyHints.${name}`)}
                {...register(name)}
              />
            ))}
            <Text size="sm" c="dimmed">
              {t('newCustomer.neverCopied')}
            </Text>
          </Stack>
        )}

        {step === 3 && (
          <Stack gap="sm" maw={560}>
            <Checkbox label={t('newCustomer.invite')} {...register('invite')} />
            {invite && (
              <>
                <TextInput
                  label={t('users.invite.email')}
                  type="email"
                  error={errors.email?.message}
                  {...register('email')}
                />
                <TextInput
                  label={t('users.invite.name')}
                  error={errors.loginName?.message}
                  {...register('loginName')}
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
                    />
                  )}
                />
              </>
            )}
          </Stack>
        )}

        {problem && <Alert color="red">{problem}</Alert>}
        <Group>
          {position > 0 && (
            <Button
              variant="default"
              onClick={() => {
                setStep(steps[position - 1] ?? 0);
              }}
            >
              {t('newCustomer.back')}
            </Button>
          )}
          <Button type="submit" loading={create.isPending}>
            {last
              ? t(mode === 'copy' ? 'newCustomer.submitCopy' : 'newCustomer.submitNew')
              : t('newCustomer.next')}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

function Created({ created }: { created: CustomerCreated }) {
  const { t } = useTranslation();
  const { customer, jobId, failed } = created;
  const job = useCustomerJob(customer.id, jobId);
  const status = job.data?.status;
  const result = job.data?.result ?? {};
  const copied = Array.isArray(result.code_lists) ? result.code_lists.length : 0;
  return (
    <Stack gap="md" maw={720}>
      <Alert color="green" title={t('newCustomer.created', { name: customer.name })}>
        {t('newCustomer.createdText', { ico: customer.ico })}
      </Alert>
      {jobId && (
        <Stack gap="xs">
          <Title order={2} size="h4">
            {t('newCustomer.copyTitle')}
          </Title>
          {status === 'succeeded' ? (
            <Text role="status">
              {t('newCustomer.copyDone', {
                lists: copied,
                templates: Number(result.templates ?? 0),
              })}
            </Text>
          ) : status === 'failed' || status === 'cancelled' ? (
            <Alert color="red" role="status">
              {t('newCustomer.copyFailed')}
            </Alert>
          ) : (
            <Group gap="sm">
              <Loader size="sm" aria-hidden />
              <Text role="status">{t('newCustomer.copying')}</Text>
            </Group>
          )}
        </Stack>
      )}
      {failed.variableNumber !== undefined && (
        <Alert color="orange">{t('newCustomer.variableNumberFailed')}</Alert>
      )}
      {failed.invite !== undefined && <Alert color="orange">{t('newCustomer.inviteFailed')}</Alert>}
      <Group>
        <ButtonLink to="/c/$customerId" params={{ customerId: customer.id }}>
          {t('newCustomer.open')}
        </ButtonLink>
        <ButtonLink variant="default" to="/users">
          {t('newCustomer.toUsers')}
        </ButtonLink>
      </Group>
    </Stack>
  );
}
