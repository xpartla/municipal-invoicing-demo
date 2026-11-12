import {
  Anchor,
  Group,
  Paper,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { Pager } from '../components/Pager';
import { AnchorLink } from '../components/RouterLinks';
import { ScrollTable } from '../components/ScrollTable';
import {
  FILES_PAGE,
  KINDS,
  downloadUrl,
  useFiles,
  type StoredFile,
} from '../features/reporting/api';
import { formatDateTime, formatSize } from '../lib/format';
import { Loading, LoadFailed } from '../components/QueryStates';

/**
 * Úložisko (plan §10.7): the customer's files, the uploaded documents, the imported and the
 * exported ones, with their size and what uses them (the invoice a document became, an
 * import's type, how many invoices an export holds), each downloadable; the totals by kind
 * and in all. The kind filter and the page are in the URL.
 */
export function FilesPage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId/files' });
  const search = useSearch({ from: '/_app/c/$customerId/files' });
  const navigate = useNavigate({ from: '/c/$customerId/files' });
  const found = useFiles(customerId, search.kind, search.page ?? 1);
  const listing = found.data;

  const uses = (file: StoredFile) => {
    if (file.kind === 'document') {
      return file.invoice_id ? (
        <AnchorLink
          to="/c/$customerId/invoices/$invoiceId"
          params={{ customerId, invoiceId: file.invoice_id }}
          size="sm"
        >
          {t('files.uses.invoice')}
        </AnchorLink>
      ) : (
        <Text size="sm" c="dimmed">
          {t('files.uses.none')}
        </Text>
      );
    }
    if (file.kind === 'import') {
      return (
        <Text size="sm">
          {t('files.uses.import', {
            type: t(`exchange.types.${file.detail ?? ''}` as 'exchange.types.accounts', {
              defaultValue: file.detail ?? '',
            }),
          })}
        </Text>
      );
    }
    return <Text size="sm">{t('files.uses.export', { count: Number(file.detail ?? 0) })}</Text>;
  };

  return (
    <Stack gap="md">
      <Title order={1}>{t('files.title')}</Title>
      <Text size="sm">{t('files.intro')}</Text>
      {found.isPending && <Loading />}
      {found.isError && <LoadFailed error={found.error} onRetry={found.refetch} />}
      {listing && (
        <>
          <SimpleGrid
            cols={{ base: 2, sm: 4 }}
            spacing="sm"
            role="list"
            aria-label={t('files.totals')}
          >
            <Paper withBorder p="sm" radius="md" role="listitem">
              <Text size="xs" c="dimmed">
                {t('files.all')}
              </Text>
              <Text fw={600}>{formatSize(listing.size)}</Text>
              <Text size="xs">
                {t('files.count', {
                  count: KINDS.reduce((n, k) => n + (listing.kinds[k]?.count ?? 0), 0),
                })}
              </Text>
            </Paper>
            {KINDS.map((kind) => (
              <Paper key={kind} withBorder p="sm" radius="md" role="listitem">
                <Text size="xs" c="dimmed">
                  {t(`files.kinds.${kind}`)}
                </Text>
                <Text fw={600}>{formatSize(listing.kinds[kind]?.size ?? 0)}</Text>
                <Text size="xs">
                  {t('files.count', { count: listing.kinds[kind]?.count ?? 0 })}
                </Text>
              </Paper>
            ))}
          </SimpleGrid>

          <Group>
            <SegmentedControl
              aria-label={t('files.filter')}
              value={search.kind ?? 'all'}
              onChange={(value) => {
                void navigate({
                  search: { kind: KINDS.find((kind) => kind === value) },
                  replace: true,
                });
              }}
              data={[
                { value: 'all', label: t('files.all') },
                ...KINDS.map((kind) => ({ value: kind, label: t(`files.kinds.${kind}`) })),
              ]}
            />
          </Group>

          {listing.items.length === 0 ? (
            <Text c="dimmed">{t('files.empty')}</Text>
          ) : (
            <ScrollTable label={t('files.table')} minWidth={640}>
              <Table striped verticalSpacing="xs" aria-label={t('files.table')}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th scope="col">{t('files.columns.name')}</Table.Th>
                    <Table.Th scope="col">{t('files.columns.kind')}</Table.Th>
                    <Table.Th scope="col" style={{ textAlign: 'right' }}>
                      {t('files.columns.size')}
                    </Table.Th>
                    <Table.Th scope="col">{t('files.columns.created')}</Table.Th>
                    <Table.Th scope="col">{t('files.columns.uses')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {listing.items.map((file) => (
                    <Table.Tr key={`${file.kind}-${file.id}`}>
                      <Table.Td>
                        <Anchor
                          href={downloadUrl(customerId, file)}
                          size="sm"
                          aria-label={t('files.download', { name: file.name })}
                        >
                          <Group gap={4} component="span" wrap="nowrap">
                            <IconDownload size={14} aria-hidden />
                            {file.name}
                          </Group>
                        </Anchor>
                      </Table.Td>
                      <Table.Td>{t(`files.kinds.${file.kind}`)}</Table.Td>
                      <Table.Td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {formatSize(file.size)}
                      </Table.Td>
                      <Table.Td style={{ whiteSpace: 'nowrap' }}>
                        {formatDateTime(file.created_at)}
                      </Table.Td>
                      <Table.Td>{uses(file)}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollTable>
          )}
          <Pager
            page={search.page ?? 1}
            pages={Math.ceil(listing.total / FILES_PAGE)}
            onPage={(page) => {
              void navigate({
                search: { kind: search.kind, page: page > 1 ? page : undefined },
              });
            }}
          />
        </>
      )}
    </Stack>
  );
}
