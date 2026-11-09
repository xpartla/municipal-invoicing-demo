import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from '@mantine/core';
import { IconAdjustments } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import type { ColumnMapping, FieldSource, ImportPreview } from './api';
import { choiceOf, choiceValue, missingRequired, setField, withChoice } from './mapping';
import { useTransformSummary } from './texts';
import { TransformDialog } from './TransformDialog';

interface Props {
  preview: ImportPreview;
  mapping: ColumnMapping;
  onMapping: (mapping: ColumnMapping) => void;
  onBack: () => void;
  onDryRun: () => void;
  running: boolean;
  problem: string | null;
}

/** Step 3: each target field gets a column, a fixed value or nothing, and the transforms
 * that clean its value. The suggestion comes from a template the headers chose, or from the
 * header names. */
export function MappingStep({
  preview,
  mapping,
  onMapping,
  onBack,
  onDryRun,
  running,
  problem,
}: Props) {
  const { t } = useTranslation();
  const summary = useTransformSummary();
  const [editing, setEditing] = useState<string | null>(null);
  const missing = missingRequired(mapping, preview.fields);
  const first = preview.rows[0];
  const columnIndex = new Map(preview.columns.map((c, i) => [c.key, i]));
  const options = [
    { value: 'none', label: t('exchange.mapping.none') },
    ...preview.columns.map((c) => ({
      value: `column:${c.key}`,
      label: `${c.letter} · ${c.header || t('exchange.read.noHeader')}`,
    })),
    { value: 'constant', label: t('exchange.mapping.constant') },
  ];
  const budget =
    mapping.import_type === 'budget_expense' || mapping.import_type === 'budget_income';
  const update = (name: string, source: FieldSource) => {
    onMapping(setField(mapping, name, source));
  };
  const editingField = preview.fields.find((f) => f.name === editing);

  return (
    <Stack gap="md">
      {preview.template_name ? (
        <Alert color="blue" title={t('exchange.mapping.fromTemplate')}>
          {preview.template_name}
        </Alert>
      ) : (
        <Text size="sm">{t('exchange.mapping.fromHeaders')}</Text>
      )}
      <ScrollTable label={t('exchange.mapping.tableLabel')} minWidth={880}>
        <Table withTableBorder verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th scope="col">{t('exchange.mapping.field')}</Table.Th>
              <Table.Th scope="col">{t('exchange.mapping.source')}</Table.Th>
              <Table.Th scope="col">{t('exchange.mapping.transforms')}</Table.Th>
              <Table.Th scope="col">{t('exchange.mapping.sample')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {preview.fields.map((field) => {
              const source = mapping.fields?.[field.name];
              const choice = choiceOf(source);
              const label = t(`exchange.fields.${field.name}` as 'exchange.fields.su');
              const index = choice.kind === 'column' ? columnIndex.get(choice.column) : undefined;
              const sample =
                choice.kind === 'constant'
                  ? (source?.constant ?? '')
                  : index !== undefined
                    ? (first?.cells[index] ?? '')
                    : '';
              return (
                <Table.Tr key={field.name}>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Text fw={500}>{label}</Text>
                      {field.required && !field.derived && (
                        <Badge size="xs" color="red" variant="light">
                          {t('exchange.mapping.required')}
                        </Badge>
                      )}
                      {field.key && (
                        <Badge size="xs" variant="light">
                          {t('exchange.mapping.key')}
                        </Badge>
                      )}
                      {field.line && (
                        <Badge size="xs" color="grape" variant="light">
                          {t('exchange.mapping.line')}
                        </Badge>
                      )}
                    </Group>
                    {field.derived && (
                      <Text size="xs" c="dimmed">
                        {field.name === 'code'
                          ? t('exchange.mapping.derived.code')
                          : t('exchange.mapping.derivedAny')}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Stack gap={4}>
                      <Select
                        aria-label={t('exchange.mapping.sourceOf', { field: label })}
                        data={options}
                        value={choiceValue(choice)}
                        allowDeselect={false}
                        searchable
                        onChange={(value) => {
                          if (value) update(field.name, withChoice(source, value));
                        }}
                        error={missing.includes(field.name) ? t('exchange.mapping.missing') : null}
                      />
                      {choice.kind === 'constant' && (
                        <TextInput
                          aria-label={t('exchange.mapping.constantOf', { field: label })}
                          value={source?.constant ?? ''}
                          onChange={(event) => {
                            update(field.name, {
                              column: null,
                              constant: event.currentTarget.value,
                              transforms: source?.transforms ?? [],
                            });
                          }}
                        />
                      )}
                    </Stack>
                  </Table.Td>
                  <Table.Td>
                    <Group gap="xs" wrap="nowrap">
                      <Text size="sm" c={source?.transforms.length ? undefined : 'dimmed'}>
                        {summary(source?.transforms ?? [])}
                      </Text>
                      <Button
                        size="compact-sm"
                        variant="subtle"
                        leftSection={<IconAdjustments size={14} aria-hidden />}
                        aria-label={t('exchange.mapping.editTransforms', { field: label })}
                        onClick={() => {
                          setEditing(field.name);
                        }}
                      >
                        {t('exchange.mapping.edit')}
                      </Button>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {sample}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </ScrollTable>
      <Group gap="lg" wrap="wrap">
        <Checkbox
          label={t('exchange.mapping.skipEmptyKey')}
          checked={mapping.skip_empty_key}
          onChange={(event) => {
            onMapping({ ...mapping, skip_empty_key: event.currentTarget.checked });
          }}
        />
        {budget && (
          <Select
            label={t('exchange.mapping.duplicates')}
            data={(['merge', 'first', 'error'] as const).map((rule) => ({
              value: rule,
              label: t(`exchange.mapping.duplicateRules.${rule}`),
            }))}
            value={mapping.duplicates ?? 'merge'}
            allowDeselect={false}
            onChange={(value) => {
              onMapping({ ...mapping, duplicates: value });
            }}
            w={320}
          />
        )}
      </Group>
      {problem && (
        <Alert color="red" title={t('exchange.mapping.refused')}>
          {problem}
        </Alert>
      )}
      <Group>
        <Button variant="default" onClick={onBack}>
          {t('exchange.mapping.back')}
        </Button>
        <Button onClick={onDryRun} loading={running} disabled={missing.length > 0}>
          {t('exchange.mapping.dryRun')}
        </Button>
      </Group>
      {editingField && (
        <TransformDialog
          field={t(`exchange.fields.${editingField.name}` as 'exchange.fields.su')}
          transforms={mapping.fields?.[editingField.name]?.transforms ?? []}
          onClose={() => {
            setEditing(null);
          }}
          onSave={(transforms) => {
            const source = mapping.fields?.[editingField.name];
            update(editingField.name, {
              column: source?.column ?? null,
              constant: source?.constant ?? null,
              transforms,
            });
            setEditing(null);
          }}
        />
      )}
    </Stack>
  );
}
