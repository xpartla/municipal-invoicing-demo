import { ActionIcon, Badge, Group, Menu, Table, VisuallyHidden } from '@mantine/core';
import { IconDots } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { formatAmount } from '../../lib/format';
import type { Entry } from './api';
import { valueText, type FieldSpec } from './kinds';

/** A code list's rows. Inactive rows stay in the list, greyed, with a badge (plan §2
 * decision 57). With `onAction`, each row has a menu to edit, deactivate or reactivate it. */
export function EntryTable({
  label,
  fields,
  entries,
  onAction,
}: {
  label: string;
  fields: FieldSpec[];
  entries: Entry[];
  onAction?: (action: 'edit' | 'deactivate' | 'reactivate', entry: Entry) => void;
}) {
  const { t } = useTranslation();
  const shown = fields.filter(
    (f) =>
      !f.amount || entries.some((e) => e.values[f.name] !== null && e.values[f.name] !== undefined),
  );
  return (
    <ScrollTable label={label} minWidth={Math.max(560, shown.length * 110)}>
      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            {shown.map((field) => (
              <Table.Th key={field.name} ta={field.amount ? 'right' : undefined}>
                {t(`codelists.fields.${field.name}`)}
              </Table.Th>
            ))}
            <Table.Th>{t('codelists.state')}</Table.Th>
            {onAction && (
              <Table.Th>
                <VisuallyHidden>{t('codelists.actions')}</VisuallyHidden>
              </Table.Th>
            )}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {entries.map((entry) => (
            <Table.Tr key={entry.key} c={entry.active ? undefined : 'dimmed'}>
              {shown.map((field) => (
                <Table.Td
                  key={field.name}
                  ta={field.amount ? 'right' : undefined}
                  ff={field.code ? 'monospace' : undefined}
                  style={field.code ? { whiteSpace: 'nowrap' } : undefined}
                >
                  {cell(entry, field, t)}
                </Table.Td>
              ))}
              <Table.Td>
                {!entry.active && <Badge color="gray">{t('codelists.inactive')}</Badge>}
              </Table.Td>
              {onAction && (
                <Table.Td>
                  <Group justify="flex-end">
                    <Menu position="bottom-end" withinPortal>
                      <Menu.Target>
                        <ActionIcon
                          variant="subtle"
                          aria-label={t('codelists.rowActions', { key: entry.key })}
                        >
                          <IconDots size={18} aria-hidden />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item
                          onClick={() => {
                            onAction('edit', entry);
                          }}
                        >
                          {t('codelists.edit')}
                        </Menu.Item>
                        <Menu.Item
                          onClick={() => {
                            onAction(entry.active ? 'deactivate' : 'reactivate', entry);
                          }}
                        >
                          {entry.active ? t('codelists.deactivate') : t('codelists.reactivate')}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Group>
                </Table.Td>
              )}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollTable>
  );
}

function cell(entry: Entry, field: FieldSpec, t: ReturnType<typeof useTranslation>['t']): string {
  const value = entry.values[field.name];
  if (value === null || value === undefined) return '';
  if (field.amount) return formatAmount(value as number);
  if (field.options) return t(`codelists.accountTypes.${valueText(value)}` as 'codelists.state');
  return valueText(value);
}
