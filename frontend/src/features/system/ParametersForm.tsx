import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  Checkbox,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useEffect, useMemo } from 'react';
import { useForm, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { ApiError, fieldOf } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { useParameters, useSaveParameters } from './api';

const TEXT_FIELDS = [
  'default_zdroj',
  'default_series',
  'default_dal',
  'canteen_series',
  'canteen_dal',
] as const;
type TextField = (typeof TEXT_FIELDS)[number];

type Values = Record<TextField, string> & { vat_payer: boolean };

const ZDROJ = /^\d[0-9A-Za-z]{1,3}$/;
const ACCOUNT = /^\d{3} \d{3}$/;

/** Parametre (plan §6.4): the customer's settings for the year that the engine reads. */
export function ParametersForm({
  customerId,
  year,
  canEdit,
}: {
  customerId: string;
  year: number;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const parameters = useParameters(customerId, year);
  const save = useSaveParameters(customerId, year);
  const schema = useMemo(() => {
    const required = z.string().trim().min(1, t('errors.required'));
    return z.object({
      vat_payer: z.boolean(),
      default_zdroj: required.regex(ZDROJ, t('system.parameters.zdrojShape')),
      default_series: required,
      default_dal: required.regex(ACCOUNT, t('system.parameters.accountShape')),
      canteen_series: required,
      canteen_dal: required.regex(ACCOUNT, t('system.parameters.accountShape')),
    });
  }, [t]);
  const initial = useMemo<Values>(() => {
    const values = parameters.data?.values ?? {};
    const text = (name: TextField) => (typeof values[name] === 'string' ? values[name] : '');
    return {
      vat_payer: values.vat_payer === true,
      default_zdroj: text('default_zdroj'),
      default_series: text('default_series'),
      default_dal: text('default_dal'),
      canteen_series: text('canteen_series'),
      canteen_dal: text('canteen_dal'),
    };
  }, [parameters.data]);
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });
  useEffect(() => {
    reset(initial);
  }, [initial, reset]);

  const submit = handleSubmit(async (values) => {
    try {
      await save.mutateAsync(values);
      notify.success(t('common.saved'));
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        for (const problem of error.problems) {
          const field = fieldOf(problem).replace(/^values\./, '');
          const message = errorText(problem.type, problem.msg);
          if (field === 'vat_payer' || (TEXT_FIELDS as readonly string[]).includes(field)) {
            setError(field as Path<Values>, { message });
          } else {
            setError('root', { message });
          }
        }
        return;
      }
      notify.failure(error);
    }
  });

  if (parameters.isPending) return <Loader aria-label={t('common.loading')} />;
  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <Stack gap="md" maw={720}>
        <Text>{t('system.parameters.intro')}</Text>
        {parameters.data === null && (
          <Alert color="yellow">{t('system.parameters.none', { year })}</Alert>
        )}
        <Checkbox
          label={t('system.parameters.fields.vat_payer')}
          disabled={!canEdit}
          {...register('vat_payer')}
        />
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {TEXT_FIELDS.map((name) => (
            <TextInput
              key={name}
              label={t(`system.parameters.fields.${name}`)}
              description={t(`system.parameters.hints.${name}`)}
              readOnly={!canEdit}
              required
              error={errors[name]?.message}
              {...register(name)}
            />
          ))}
        </SimpleGrid>
        {errors.root && (
          <Alert color="red" role="alert">
            {errors.root.message}
          </Alert>
        )}
        {canEdit && (
          <Group>
            <Button
              type="submit"
              loading={isSubmitting}
              disabled={!isDirty && parameters.data !== null}
            >
              {t('common.save')}
            </Button>
          </Group>
        )}
      </Stack>
    </form>
  );
}
