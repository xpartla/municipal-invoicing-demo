import {
  Alert,
  Badge,
  Button,
  Group,
  List,
  Loader,
  NumberInput,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { ScrollTable } from '../../components/ScrollTable';
import { ApiError } from '../../lib/apiError';
import { useNotify } from '../../lib/notify';
import { useNumberSeries, useSetLastUsed, type NumberSeries } from './api';

const GAPS_SHOWN = 10;

/**
 * Číselné rady under Systém (plan §10.7, §7.2): per invoice series of the year the counter
 * (last used, next), the numbers held with what holds them, the gaps, and the audited edit of
 * the counter for those who edit code lists.
 */
export function NumberSeriesPanel({
  customerId,
  year,
  canEdit,
}: {
  customerId: string;
  year: number;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const series = useNumberSeries(customerId, year);
  const save = useSetLastUsed(customerId);
  const [editing, setEditing] = useState<NumberSeries | null>(null);
  const [value, setValue] = useState<number | string>(0);
  const [error, setError] = useState<string | null>(null);
  const [showing, setShowing] = useState<NumberSeries | null>(null);

  if (series.isPending) return <Loader size="sm" aria-label={t('common.loading')} />;
  const items = series.data?.items ?? [];

  const submit = async () => {
    if (!editing) return;
    setError(null);
    try {
      await save.mutateAsync({ series: editing.series, year, lastUsed: Number(value) });
      setEditing(null);
      notify.success(t('system.series.saved'));
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 422) {
        const type = failure.problems[0]?.type ?? 'invalid';
        setError(t(`errors.${type}` as 'errors.below_used', { defaultValue: t('common.error') }));
      } else {
        notify.failure(failure);
      }
    }
  };

  return (
    <Stack gap="md">
      <Text size="sm">{t('system.series.intro')}</Text>
      {items.length === 0 ? (
        <Text c="dimmed">{t('system.series.empty')}</Text>
      ) : (
        <ScrollTable label={t('system.series.tableLabel')} minWidth={720}>
          <Table striped verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">{t('system.series.series')}</Table.Th>
                <Table.Th scope="col">{t('system.series.pattern')}</Table.Th>
                <Table.Th scope="col">{t('system.series.lastUsed')}</Table.Th>
                <Table.Th scope="col">{t('system.series.next')}</Table.Th>
                <Table.Th scope="col">{t('system.series.used')}</Table.Th>
                <Table.Th scope="col">{t('system.series.gaps')}</Table.Th>
                {canEdit && (
                  <Table.Th scope="col">
                    <Text span size="sm" fw={700}>
                      {t('system.series.edit')}
                    </Text>
                  </Table.Th>
                )}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((s) => (
                <Table.Tr key={s.series}>
                  <Table.Td ff="monospace" fw={700}>
                    {s.series}
                  </Table.Td>
                  <Table.Td ff="monospace">{s.pattern}</Table.Td>
                  <Table.Td ff="monospace">{s.last_used_number ?? '—'}</Table.Td>
                  <Table.Td ff="monospace">{s.next_number}</Table.Td>
                  <Table.Td>
                    {s.used.length === 0 ? (
                      '—'
                    ) : (
                      <Button
                        size="compact-xs"
                        variant="subtle"
                        aria-label={t('system.series.showUsed', {
                          series: s.series,
                          count: s.used.length,
                        })}
                        onClick={() => {
                          setShowing(s);
                        }}
                      >
                        {t('system.series.usedCount', { count: s.used.length })}
                      </Button>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {s.gaps.length === 0 ? (
                      <Text size="sm" c="dimmed">
                        {t('system.series.noGaps')}
                      </Text>
                    ) : (
                      <Text size="sm" ff="monospace">
                        {s.gaps.slice(0, GAPS_SHOWN).join(', ')}
                        {s.gaps.length > GAPS_SHOWN &&
                          ` ${t('system.series.moreGaps', { count: s.gaps.length - GAPS_SHOWN })}`}
                      </Text>
                    )}
                  </Table.Td>
                  {canEdit && (
                    <Table.Td>
                      <Button
                        size="compact-xs"
                        variant="default"
                        aria-label={t('system.series.editLabel', { series: s.series })}
                        onClick={() => {
                          setValue(s.last_used);
                          setError(null);
                          setEditing(s);
                        }}
                      >
                        {t('system.series.edit')}
                      </Button>
                    </Table.Td>
                  )}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}

      <Dialog
        opened={editing !== null}
        onClose={() => {
          setEditing(null);
        }}
        title={editing ? t('system.series.editTitle', { series: editing.series, year }) : ''}
      >
        <Stack gap="md">
          <Text size="sm">{t('system.series.editText')}</Text>
          <NumberInput
            label={t('system.series.lastUsedLabel')}
            min={0}
            allowDecimal={false}
            allowNegative={false}
            value={value}
            onChange={setValue}
            error={error}
          />
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setEditing(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button loading={save.isPending} onClick={() => void submit()}>
              {t('common.save')}
            </Button>
          </Group>
        </Stack>
      </Dialog>

      <Dialog
        opened={showing !== null}
        onClose={() => {
          setShowing(null);
        }}
        title={showing ? t('system.series.usedTitle', { series: showing.series }) : ''}
      >
        <List spacing={4} size="sm">
          {(showing?.used ?? []).map((u) => (
            <List.Item key={u.number}>
              <Group gap="xs">
                <Text span ff="monospace">
                  {u.number}
                </Text>
                <Text span c="dimmed">
                  {t(`system.series.kinds.${u.kind}`)}
                </Text>
                {u.frozen && <Badge color="gray">{t('system.series.frozen')}</Badge>}
              </Group>
            </List.Item>
          ))}
        </List>
      </Dialog>
      {series.isError && <Alert color="red">{t('common.error')}</Alert>}
    </Stack>
  );
}
