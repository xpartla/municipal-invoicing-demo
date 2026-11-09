import { Stack, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { useMe } from '../features/identity/api';
import { NewCustomerWizard } from '../features/tenancy/NewCustomerWizard';

/** Nový klient (plan §9.3, §10.8): staff and admins create a customer, new or as a copy. */
export function NewCustomerPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  return (
    <Stack gap="md">
      <Title order={1}>{t('newCustomer.title')}</Title>
      {me && <NewCustomerWizard me={me} />}
    </Stack>
  );
}
