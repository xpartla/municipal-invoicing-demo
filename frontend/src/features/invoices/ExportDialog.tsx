import { Alert, Anchor, Button, Group, Loader, SegmentedControl, Stack, Text } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import { useNotify } from '../../lib/notify';
import {
  exportFileUrl,
  useExportPreview,
  useExportRun,
  useStartExport,
  type ExportFormat,
  type ExportScope,
} from './api';

/**
 * The export dialog (plan §7.4): CSV or XLSX of a selection or of the table's filters. It first
 * says what the file will hold, with the "already exported" notice; then it follows the job
 * and offers the file.
 */
export function ExportDialog({
  customerId,
  scope,
  onClose,
}: {
  customerId: string;
  scope: ExportScope | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const [format, setFormat] = useState<ExportFormat>('csv');
  const [runId, setRunId] = useState<string | undefined>();
  const preview = useExportPreview(
    customerId,
    scope ?? { invoiceIds: [] },
    scope !== null && runId === undefined,
  );
  const start = useStartExport(customerId);
  const run = useExportRun(customerId, runId);
  const close = () => {
    setRunId(undefined);
    setFormat('csv');
    onClose();
  };
  const found = preview.data;
  const state = run.data?.state;

  return (
    <Dialog opened={scope !== null} onClose={close} title={t('invoices.export.title')} size="lg">
      <Stack gap="md">
        <Text size="sm">
          {scope && 'invoiceIds' in scope
            ? t('invoices.export.scopeSelection')
            : t('invoices.export.scopeFilter')}
        </Text>
        {runId === undefined && (
          <>
            <Stack gap={4}>
              <Text size="sm" fw={500} id="export-format">
                {t('invoices.export.format')}
              </Text>
              <SegmentedControl
                aria-labelledby="export-format"
                value={format}
                onChange={(value) => {
                  setFormat(value);
                }}
                data={[
                  { value: 'csv', label: t('invoices.export.csv') },
                  { value: 'xlsx', label: t('invoices.export.xlsx') },
                ]}
              />
            </Stack>
            {preview.isPending && <Loader size="sm" aria-label={t('common.loading')} />}
            {found && (
              <Stack gap={4} aria-live="polite">
                {found.invoices > 0 ? (
                  <Text>{t('invoices.export.invoices', { count: found.invoices })}</Text>
                ) : (
                  <Alert color="orange">{t('invoices.export.none')}</Alert>
                )}
                {found.again > 0 && (
                  <Alert color="yellow">{t('invoices.export.again', { count: found.again })}</Alert>
                )}
                {found.skipped > 0 && (
                  <Text size="sm" c="dimmed">
                    {t('invoices.export.skipped', { count: found.skipped })}
                  </Text>
                )}
              </Stack>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                {t('common.cancel')}
              </Button>
              <Button
                disabled={!found || found.invoices === 0}
                loading={start.isPending}
                onClick={() => {
                  if (!scope) return;
                  start.mutate(
                    { format, scope },
                    {
                      onSuccess: (started) => {
                        setRunId(started.id);
                      },
                      onError: notify.failure,
                    },
                  );
                }}
              >
                {t('invoices.export.start')}
              </Button>
            </Group>
          </>
        )}
        {runId !== undefined && (
          <Stack gap="sm" aria-live="polite">
            {(state === undefined || state === 'queued') && (
              <Group gap="xs">
                <Loader size="sm" aria-hidden />
                <Text>{t('invoices.export.running')}</Text>
              </Group>
            )}
            {state === 'done' && run.data?.file_name && (
              <>
                <Alert color="green">{t('invoices.export.done')}</Alert>
                <Anchor href={exportFileUrl(customerId, runId)} download={run.data.file_name}>
                  <Group gap={6}>
                    <IconDownload size={16} aria-hidden />
                    {t('invoices.export.download', { file: run.data.file_name })}
                  </Group>
                </Anchor>
              </>
            )}
            {state === 'failed' && <Alert color="red">{t('invoices.export.failed')}</Alert>}
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                {t('common.close')}
              </Button>
            </Group>
          </Stack>
        )}
      </Stack>
    </Dialog>
  );
}
