import { Stack, Tabs, Text, Title } from '@mantine/core';
import { IconKeyboard, IconUpload } from '@tabler/icons-react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { UploadPanel } from '../features/intake/UploadPanel';
import { useEnterInvoice } from '../features/invoices/api';
import { FieldsForm } from '../features/invoices/FieldsForm';
import { useNotify } from '../lib/notify';
import { ForbiddenPage } from './ForbiddenPage';

/**
 * Nová faktúra (plan §10.5, §8.5): uploading scans, photos and PDFs, each read by a job and
 * then checked; or manual entry, the field form whose invoice is checked and coded at once.
 */
export function NewInvoicePage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  const navigate = useNavigate();
  const notify = useNotify();
  const enter = useEnterInvoice(customerId);
  const customer = me?.customers.find((c) => c.id === customerId);
  if (me && !inCustomer(me, customerId, 'invoices.process')) return <ForbiddenPage />;
  return (
    <Stack gap="md">
      <Title order={1}>{t('invoices.new.title')}</Title>
      <Tabs defaultValue="upload" keepMounted>
        <Tabs.List>
          <Tabs.Tab value="upload" leftSection={<IconUpload size={16} aria-hidden />}>
            {t('invoices.new.upload')}
          </Tabs.Tab>
          <Tabs.Tab value="manual" leftSection={<IconKeyboard size={16} aria-hidden />}>
            {t('invoices.new.manual')}
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="upload" pt="md">
          <Stack gap="sm">
            <Text size="sm">{t('invoices.new.uploadIntro')}</Text>
            <UploadPanel customerId={customerId} />
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="manual" pt="md">
          <Stack gap="sm">
            <Text size="sm">{t('invoices.new.intro')}</Text>
            {customer && (
              <FieldsForm
                customer={{ name: customer.name, ico: customer.ico }}
                submitLabel={t('invoices.new.save')}
                onSubmit={async (fields) => {
                  const invoice = await enter.mutateAsync(fields);
                  notify.success(t('invoices.new.saved'));
                  await navigate({
                    to: '/c/$customerId/invoices/$invoiceId',
                    params: { customerId, invoiceId: invoice.id },
                  });
                }}
              />
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
