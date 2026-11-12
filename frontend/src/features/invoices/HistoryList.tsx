import { Table, Text } from '@mantine/core';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';
import { formatDate, formatDateTime } from '../../lib/format';
import { useHistory, type History } from './api';
import { Loading, LoadFailed } from '../../components/QueryStates';

type Entry = History['items'][number];

function details(entry: Entry, t: TFunction): string {
  const d = entry.details as Record<string, unknown>;
  const text = (key: string) => (typeof d[key] === 'string' ? d[key] : '');
  const found: string[] = [];
  if (entry.kind === 'renumbered')
    found.push(t('invoice.history.renumbered', { from: text('from'), to: text('to') }));
  else if (text('number')) found.push(t('invoice.history.number', { number: text('number') }));
  if (text('action') === 'accepted') found.push(t('invoice.history.accepted'));
  if (text('action') === 'corrected') found.push(t('invoice.history.corrected'));
  if (text('paid_on'))
    found.push(t('invoice.history.paidOn', { date: formatDate(text('paid_on')) }));
  if (d.again === true) found.push(t('invoice.history.again'));
  if (text('reason')) found.push(t('invoice.history.reason', { reason: text('reason') }));
  return found.join(' · ');
}

/** História (plan §10.4): each step with its time, who took it (an admin impersonating shows
 * as "admin ako user") and what it did. */
export function HistoryList({ customerId, invoiceId }: { customerId: string; invoiceId: string }) {
  const { t } = useTranslation();
  const history = useHistory(customerId, invoiceId, true);
  if (history.isPending) return <Loading />;
  if (history.isError) return <LoadFailed error={history.error} onRetry={history.refetch} />;
  const items = history.data.items;
  if (items.length === 0) return <Text c="dimmed">{t('invoice.history.empty')}</Text>;
  const names = history.data.names;
  const who = (entry: Entry) => {
    const user = entry.actor_id
      ? (names[entry.actor_id] ?? entry.actor_id)
      : t('invoice.history.system');
    if (!entry.real_actor_id) return user;
    return t('invoice.history.asUser', {
      admin: names[entry.real_actor_id] ?? entry.real_actor_id,
      user,
    });
  };
  return (
    <ScrollTable label={t('invoice.tabs.history')} minWidth={560}>
      <Table striped verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th scope="col">{t('invoice.history.when')}</Table.Th>
            <Table.Th scope="col">{t('invoice.history.what')}</Table.Th>
            <Table.Th scope="col">{t('invoice.history.who')}</Table.Th>
            <Table.Th scope="col">{t('invoice.history.details')}</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {items.map((entry, i) => (
            <Table.Tr key={i}>
              <Table.Td>{formatDateTime(entry.at)}</Table.Td>
              <Table.Td>{t(`invoice.history.kinds.${entry.kind}`)}</Table.Td>
              <Table.Td>{who(entry)}</Table.Td>
              <Table.Td>{details(entry, t)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollTable>
  );
}
