import { Badge, Button, Stack, Table, Text, Title } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { ScrollTable } from '../../components/ScrollTable';
import { formatDateTime } from '../../lib/format';
import { useDiff, useVersions, type Diff, type Entry, type Version } from './api';
import { valueText, type CustomerKind } from './kinds';
import { Loading, LoadFailed } from '../../components/QueryStates';

/** Verzie a zmeny (plan §6.2, §10.6): every version of the list for the year, and what each
 * changed against the one before. */
export function HistoryDialog({
  customerId,
  kind,
  year,
  opened,
  onClose,
}: {
  customerId: string;
  kind: CustomerKind;
  year: number;
  opened: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const versions = useVersions({ customerId }, kind, year, opened);
  const [compared, setCompared] = useState<{ old: Version; current: Version } | undefined>();
  const diff = useDiff(customerId, kind, compared?.old.id, compared?.current.id);
  const list = versions.data ?? [];
  return (
    <Dialog
      opened={opened}
      onClose={() => {
        setCompared(undefined);
        onClose();
      }}
      size="xl"
      title={t('codelists.history.title', { list: t(`codelists.kinds.${kind}`) })}
    >
      <Stack gap="md">
        {versions.isPending ? (
          <Loading />
        ) : versions.isError ? (
          <LoadFailed error={versions.error} onRetry={versions.refetch} />
        ) : (
          <ScrollTable label={t('codelists.history.versions')} minWidth={560}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('codelists.history.number')}</Table.Th>
                  <Table.Th>{t('codelists.history.created')}</Table.Th>
                  <Table.Th>{t('codelists.history.origin')}</Table.Th>
                  <Table.Th>{t('codelists.history.rows')}</Table.Th>
                  <Table.Th>{t('codelists.history.changes')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {list.map((version, index) => {
                  const previous = list[index + 1];
                  return (
                    <Table.Tr key={version.id}>
                      <Table.Td>
                        {version.number}{' '}
                        {version.status === 'active' && (
                          <Badge color="green">{t('codelists.history.active')}</Badge>
                        )}
                      </Table.Td>
                      <Table.Td>{formatDateTime(version.created_at)}</Table.Td>
                      <Table.Td>{t(`codelists.origins.${version.origin}`)}</Table.Td>
                      <Table.Td>{version.entry_count}</Table.Td>
                      <Table.Td>
                        {previous && (
                          <Button
                            size="xs"
                            variant="default"
                            onClick={() => {
                              setCompared({ old: previous, current: version });
                            }}
                          >
                            {t('codelists.history.compare', {
                              number: version.number,
                              previous: previous.number,
                            })}
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </ScrollTable>
        )}
        {compared && (
          <section
            aria-label={t('codelists.history.diffTitle', {
              number: compared.current.number,
              previous: compared.old.number,
            })}
          >
            <Title order={3} size="h4" mb="xs">
              {t('codelists.history.diffTitle', {
                number: compared.current.number,
                previous: compared.old.number,
              })}
            </Title>
            {diff.isPending ? (
              <Loading />
            ) : diff.isError ? (
              <LoadFailed error={diff.error} onRetry={diff.refetch} />
            ) : (
              <DiffList diff={diff.data} />
            )}
          </section>
        )}
      </Stack>
    </Dialog>
  );
}

function describe(entry: Entry): string {
  const text = entry.values.description ?? entry.values.name;
  return typeof text === 'string' && text ? `${entry.key} · ${text}` : entry.key;
}

function DiffList({ diff }: { diff: Diff }) {
  const { t } = useTranslation();
  if (!diff.added.length && !diff.removed.length && !diff.changed.length) {
    return <Text>{t('codelists.history.noChanges')}</Text>;
  }
  return (
    <Stack gap="xs">
      {diff.added.map((entry) => (
        <Text key={`a-${entry.key}`}>
          <Badge color="green" mr="xs">
            {t('codelists.history.added')}
          </Badge>
          {describe(entry)}
        </Text>
      ))}
      {diff.removed.map((entry) => (
        <Text key={`r-${entry.key}`}>
          <Badge color="red" mr="xs">
            {t('codelists.history.removed')}
          </Badge>
          {describe(entry)}
        </Text>
      ))}
      {diff.changed.map((change) => (
        <Stack key={`c-${change.key}`} gap={2}>
          <Text>
            <Badge color="blue" mr="xs">
              {t('codelists.history.changed')}
            </Badge>
            {change.key}
          </Text>
          {Object.keys(change.after.values)
            .filter(
              (name) =>
                JSON.stringify(change.before.values[name]) !==
                JSON.stringify(change.after.values[name]),
            )
            .map((name) => (
              <Text key={name} size="sm" pl="lg">
                {t(`codelists.fields.${name}` as 'codelists.fields.name', { defaultValue: name })}:{' '}
                {show(change.before.values[name])} → {show(change.after.values[name])}
              </Text>
            ))}
        </Stack>
      ))}
    </Stack>
  );
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? '✓' : '✗';
  return valueText(value);
}
