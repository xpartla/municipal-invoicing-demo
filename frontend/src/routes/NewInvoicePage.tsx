import { Alert, Stack, Title } from '@mantine/core';
import { useNavigate, useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { useEnterInvoice } from '../features/invoices/api';
import { FieldsForm } from '../features/invoices/FieldsForm';
import { useNotify } from '../lib/notify';
import { ForbiddenPage } from './ForbiddenPage';

/**
 * Nová faktúra (plan §10.5, §8.5). Until uploads come (P2-M5) it is manual entry: the field
 * form, whose invoice is checked and coded at once; then its detail opens with the proposal.
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
      <Alert color="blue">{t('invoices.new.intro')}</Alert>
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
  );
}
