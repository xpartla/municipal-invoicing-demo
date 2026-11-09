import { ActionIcon, Anchor, Badge, Group, Loader, Stack, Table, Text, Title } from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useParams } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '../components/ConfirmDialog';
import { Pager } from '../components/Pager';
import { AnchorLink, ButtonLink } from '../components/RouterLinks';
import { ScrollTable } from '../components/ScrollTable';
import {
  fileUrl,
  useDeleteTemplate,
  useImports,
  useTemplates,
  type ImportRun,
  type Template,
} from '../features/exchange/api';
import { useMe } from '../features/identity/api';
import { inAnyProvider, inCustomer, onPlatform } from '../features/identity/capabilities';
import { formatDateTime } from '../lib/format';
import { useNotify } from '../lib/notify';

const SIZE = 20;

const STATE_COLORS: Record<ImportRun['state'], string> = {
  uploaded: 'gray',
  mapped: 'blue',
  dry_run_ok: 'teal',
  dry_run_failed: 'orange',
  applied: 'green',
  cancelled: 'gray',
};

/** Importy a exporty (plan §10.7): the customer's import runs with their state, report and
 * file; "Nový import"; the mapping templates the customer may use. Exports come with the
 * invoices (P2-M4). */
export function ExchangePage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  const owner = { customerId };
  const [page, setPage] = useState(1);
  const runs = useImports(owner, page, SIZE);
  const canImport = me ? inCustomer(me, customerId, 'codelists.edit') : false;
  const canUseTemplates = me ? inCustomer(me, customerId, 'templates.use') : false;

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end">
        <Title order={1}>{t('exchange.title')}</Title>
        {canImport && (
          <ButtonLink
            to="/c/$customerId/exchange/import"
            params={{ customerId }}
            search={{}}
            leftSection={<IconPlus size={16} aria-hidden />}
          >
            {t('exchange.newImport')}
          </ButtonLink>
        )}
      </Group>
      <Stack gap="sm">
        <Title order={2} size="h3">
          {t('exchange.history.title')}
        </Title>
        {runs.isPending ? (
          <Loader aria-label={t('common.loading')} />
        ) : (runs.data?.items ?? []).length === 0 ? (
          <Text>{t('exchange.history.empty')}</Text>
        ) : (
          <>
            <ScrollTable label={t('exchange.history.title')} minWidth={900}>
              <Table striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th scope="col">{t('exchange.history.when')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.type')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.year')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.file')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.state')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.result')}</Table.Th>
                    <Table.Th scope="col">{t('exchange.history.actions')}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {(runs.data?.items ?? []).map((run) => (
                    <Table.Tr key={run.id}>
                      <Table.Td>{formatDateTime(run.created_at)}</Table.Td>
                      <Table.Td>{t(`exchange.types.${run.import_type}`)}</Table.Td>
                      <Table.Td>{run.year}</Table.Td>
                      <Table.Td>
                        <Anchor href={fileUrl(owner, run.id)} download>
                          {run.file.name}
                        </Anchor>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={STATE_COLORS[run.state]} variant="light">
                          {t(`exchange.states.${run.state}`)}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        {run.report
                          ? t('exchange.history.counts', {
                              entries: run.report.entries,
                              errors: run.report.errors.length,
                              warnings: run.report.warnings.length,
                            })
                          : '—'}
                      </Table.Td>
                      <Table.Td>
                        {canImport && run.state !== 'cancelled' && (
                          <AnchorLink
                            to="/c/$customerId/exchange/import"
                            params={{ customerId }}
                            search={{ run: run.id }}
                            aria-label={t('exchange.history.openLabel', { file: run.file.name })}
                          >
                            {run.state === 'applied'
                              ? t('exchange.history.show')
                              : t('exchange.history.continue')}
                          </AnchorLink>
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
      <Stack gap="sm">
        <Title order={2} size="h3">
          {t('exchange.exports.title')}
        </Title>
        <Text>{t('exchange.exports.soon')}</Text>
      </Stack>
      {canUseTemplates && <Templates customerId={customerId} />}
    </Stack>
  );
}

function Templates({ customerId }: { customerId: string }) {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const notify = useNotify();
  const owner = { customerId };
  const templates = useTemplates(owner);
  const remove = useDeleteTemplate(owner);
  const [deleting, setDeleting] = useState<Template | null>(null);
  const mayDelete = (template: Template) => {
    if (!me || template.builtin) return false;
    if (template.scope === 'customer')
      return inCustomer(me, customerId, 'templates.create_customer');
    if (template.scope === 'provider')
      return (
        inAnyProvider(me, 'templates.create_provider') ||
        onPlatform(me, 'templates.create_provider')
      );
    return onPlatform(me, 'templates.create_global');
  };

  return (
    <Stack gap="sm">
      <Title order={2} size="h3">
        {t('exchange.templates.title')}
      </Title>
      <Text size="sm">{t('exchange.templates.intro')}</Text>
      {templates.isPending ? (
        <Loader aria-label={t('common.loading')} />
      ) : (
        <ScrollTable label={t('exchange.templates.title')} minWidth={760}>
          <Table striped withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">{t('exchange.templates.name')}</Table.Th>
                <Table.Th scope="col">{t('exchange.templates.type')}</Table.Th>
                <Table.Th scope="col">{t('exchange.templates.scope')}</Table.Th>
                <Table.Th scope="col">{t('exchange.templates.updated')}</Table.Th>
                <Table.Th scope="col">{t('exchange.history.actions')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(templates.data ?? []).map((template) => (
                <Table.Tr key={template.id}>
                  <Table.Td>{template.name}</Table.Td>
                  <Table.Td>{t(`exchange.types.${template.import_type}`)}</Table.Td>
                  <Table.Td>{t(`exchange.scopes.${template.scope}`)}</Table.Td>
                  <Table.Td>
                    {template.builtin ? '—' : formatDateTime(template.updated_at)}
                  </Table.Td>
                  <Table.Td>
                    {mayDelete(template) && (
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        aria-label={t('exchange.templates.delete', { name: template.name })}
                        onClick={() => {
                          setDeleting(template);
                        }}
                      >
                        <IconTrash size={16} aria-hidden />
                      </ActionIcon>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
      {deleting && (
        <ConfirmDialog
          opened
          title={t('exchange.templates.deleteTitle')}
          message={t('exchange.templates.deleteMessage', { name: deleting.name })}
          confirmLabel={t('exchange.templates.deleteConfirm')}
          danger
          loading={remove.isPending}
          onClose={() => {
            setDeleting(null);
          }}
          onConfirm={() => {
            remove.mutate(deleting.id, {
              onSuccess: () => {
                notify.success(t('exchange.templates.deleted'));
                setDeleting(null);
              },
              onError: (error) => {
                notify.failure(error);
              },
            });
          }}
        />
      )}
    </Stack>
  );
}
