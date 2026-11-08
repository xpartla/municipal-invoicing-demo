import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, Button, Group, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { useEffect, useMemo } from 'react';
import { Controller, useForm, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';

import { Dialog } from '../../components/Dialog';
import { ApiError, fieldOf } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useErrorText } from '../../lib/useErrorText';
import { useEditRow, type Entry } from './api';
import { FIELDS, parseAmount, valueText, type CustomerKind, type FieldName } from './kinds';

type Values = Partial<Record<FieldName, string>>;

/**
 * Pridať or upraviť riadok (plan §10.6). Saving makes a new version of the list; `versionId`
 * is the active version the user is looking at, so an edit someone else saved first is
 * refused (409) instead of lost.
 */
export function EntryDialog({
  customerId,
  kind,
  year,
  versionId,
  entry,
  opened,
  onClose,
}: {
  customerId: string;
  kind: CustomerKind;
  year: number;
  versionId: string | null;
  /** The row to edit; undefined to add one. */
  entry: Entry | undefined;
  opened: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const notify = useNotify();
  const edit = useEditRow(customerId, kind, year);
  const fields = FIELDS[kind];
  const schema = useMemo(
    () =>
      z.object(
        Object.fromEntries(
          fields.map((f) => {
            let rule = z.string().trim();
            if (f.required) rule = rule.min(1, t('errors.required'));
            if (f.digits !== undefined) {
              const digits = f.digits;
              rule = rule.refine(
                (v) => v === '' || new RegExp(`^\\d{${String(digits)}}$`).test(v),
                {
                  message: t('codelists.digits', { count: digits }),
                },
              );
            }
            if (f.amount) {
              rule = rule.refine((v) => v === '' || /^-?\d+([.,]\d{1,2})?$/.test(parseAmount(v)), {
                message: t('codelists.amount'),
              });
            }
            return [f.name, rule];
          }),
        ),
      ),
    [fields, t],
  );
  const initial = useMemo(
    () =>
      Object.fromEntries(
        fields.map((f) => {
          const value = entry?.values[f.name];
          return [f.name, valueText(value)];
        }),
      ) as Values,
    [fields, entry],
  );
  const {
    register,
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: initial });
  useEffect(() => {
    reset(initial);
  }, [initial, reset]);

  const submit = handleSubmit(async (form) => {
    const values: Record<string, unknown> = {};
    for (const f of fields) {
      const text = (form[f.name] ?? '').trim();
      values[f.name] = text === '' ? null : f.amount ? parseAmount(text) : text;
    }
    try {
      await edit.mutateAsync({
        edit: entry ? { action: 'edit', key: entry.key, values } : { action: 'add', values },
        versionId,
      });
      notify.success(t('codelists.saved'));
      onClose();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError('root', { message: t('codelists.conflict') });
        return;
      }
      if (error instanceof ApiError && error.status === 422) {
        for (const problem of error.problems) {
          const field = fieldOf(problem).replace(/^values\./, '');
          const message = errorText(problem.type, problem.msg);
          if (fields.some((f) => f.name === field)) {
            setError(field as Path<Values>, { type: problem.type, message });
          } else {
            setError('root', { type: problem.type, message });
          }
        }
        return;
      }
      notify.failure(error);
    }
  });

  return (
    <Dialog
      opened={opened}
      onClose={onClose}
      size="lg"
      title={entry ? t('codelists.editTitle', { key: entry.key }) : t('codelists.addTitle')}
    >
      <form onSubmit={(event) => void submit(event)} noValidate>
        <Stack gap="sm">
          <Text size="sm">{t('codelists.versionNote')}</Text>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {fields.map((field) =>
              field.options ? (
                <Controller
                  key={field.name}
                  control={control}
                  name={field.name}
                  render={({ field: input }) => (
                    <Select
                      label={t(`codelists.fields.${field.name}`)}
                      required={field.required}
                      data={(field.options ?? []).map((o) => ({
                        value: o,
                        label: t(`codelists.accountTypes.${o}` as 'codelists.state'),
                      }))}
                      value={input.value ?? null}
                      onChange={(value) => {
                        input.onChange(value ?? '');
                      }}
                      error={errors[field.name]?.message}
                      allowDeselect={false}
                    />
                  )}
                />
              ) : (
                <TextInput
                  key={field.name}
                  label={t(`codelists.fields.${field.name}`)}
                  required={field.required}
                  inputMode={field.amount ? 'decimal' : undefined}
                  error={errors[field.name]?.message}
                  {...register(field.name)}
                />
              ),
            )}
          </SimpleGrid>
          {errors.root && (
            <Alert color="red" role="alert">
              {errors.root.message}
            </Alert>
          )}
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
