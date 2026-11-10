import { Anchor, Badge, Stack, Table, Text, Title } from '@mantine/core';
import type { TFunction } from 'i18next';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Pager } from '../../components/Pager';
import { ScrollTable } from '../../components/ScrollTable';
import { formatDateTime } from '../../lib/format';
import { exportFileUrl, useExports, type ExportRun } from './api';

const SIZE = 20;
const COLORS = { queued: 'blue', done: 'green', failed: 'red' } as const;

function scopeText(run: ExportRun, t: TFunction) {
  return 'invoice_ids' in run.scope
    ? t('exchange.exports.scopeSelection')
    : t('exchange.exports.scopeFilter');
}

/** Importy a exporty (plan §10.7): the export runs, the newest first, with their files. */
export function ExportHistory({ customerId }: { customerId: string }) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const runs = useExports(customerId, page, SIZE);
  const items = runs.data?.items ?? [];
  return (
    <Stack gap="sm">
      <Title order={2} size="h3">
        {t('exchange.exports.title')}
      </Title>
      {runs.isSuccess && items.length === 0 ? (
        <Text c="dimmed">{t('exchange.exports.empty')}</Text>
      ) : (
        <>
          <ScrollTable label={t('exchange.exports.title')} minWidth={620}>
            <Table striped verticalSpacing="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">{t('exchange.exports.when')}</Table.Th>
                  <Table.Th scope="col">{t('exchange.exports.scope')}</Table.Th>
                  <Table.Th scope="col">{t('exchange.exports.invoices')}</Table.Th>
                  <Table.Th scope="col">{t('exchange.exports.state')}</Table.Th>
                  <Table.Th scope="col">{t('exchange.exports.file')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {items.map((run) => (
                  <Table.Tr key={run.id}>
                    <Table.Td>{formatDateTime(run.created_at)}</Table.Td>
                    <Table.Td>{scopeText(run, t)}</Table.Td>
                    <Table.Td>
                      {run.state === 'done' ? run.invoices : run.requested}
                      {run.again > 0 && (
                        <Text size="xs" c="dimmed">
                          {t('exchange.exports.again', { count: run.again })}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Badge color={COLORS[run.state]}>
                        {t(`exchange.exports.states.${run.state}`)}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {run.file_name && (
                        <Anchor
                          href={exportFileUrl(customerId, run.id)}
                          download={run.file_name}
                          aria-label={t('exchange.exports.download', { file: run.file_name })}
                        >
                          {run.file_name}
                        </Anchor>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollTable>
          <Pager page={page} pages={Math.ceil((runs.data?.total ?? 0) / SIZE)} onPage={setPage} />
        </>
      )}
    </Stack>
  );
}
