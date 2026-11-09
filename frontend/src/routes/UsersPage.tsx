import { Group, Select, Stack, Tabs, Title } from '@mantine/core';
import { IconBuildingPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ButtonLink } from '../components/RouterLinks';
import { AllAccounts } from '../features/identity/AllAccounts';
import { useMe } from '../features/identity/api';
import { createsCustomers, onPlatform } from '../features/identity/capabilities';
import { Directory } from '../features/tenancy/Directory';

/**
 * Používatelia (plan §10.8–10.9): staff see their provider's customers with the logins
 * nested; admins see every customer, and every account with the admin's actions.
 */
export function UsersPage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const [providerId, setProviderId] = useState(me?.providers[0]?.id);
  if (!me) return null;
  const admin = onPlatform(me, 'provider.overview');
  const scope = admin ? 'all' : providerId ? { providerId } : undefined;
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Title order={1}>{t('users.title')}</Title>
        {createsCustomers(me) && (
          <ButtonLink to="/users/new" leftSection={<IconBuildingPlus size={16} aria-hidden />}>
            {t('newCustomer.button')}
          </ButtonLink>
        )}
      </Group>
      {!admin && me.providers.length > 1 && (
        <Select
          label={t('users.provider')}
          data={me.providers.map((p) => ({ value: p.id, label: p.name }))}
          value={providerId ?? null}
          allowDeselect={false}
          onChange={(value) => {
            if (value) setProviderId(value);
          }}
          maw={360}
        />
      )}
      {onPlatform(me, 'users.administer') ? (
        <Tabs defaultValue="customers" keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="customers">{t('users.tabs.customers')}</Tabs.Tab>
            <Tabs.Tab value="accounts">{t('users.tabs.accounts')}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="customers" pt="md">
            <Directory me={me} scope="all" />
          </Tabs.Panel>
          <Tabs.Panel value="accounts" pt="md">
            <AllAccounts me={me} />
          </Tabs.Panel>
        </Tabs>
      ) : (
        scope && <Directory me={me} scope={scope} />
      )}
    </Stack>
  );
}
