import { Select, Stack, Tabs, Title } from '@mantine/core';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AllAccounts } from '../features/identity/AllAccounts';
import { useMe } from '../features/identity/api';
import { onPlatform } from '../features/identity/capabilities';
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
      <Title order={1}>{t('users.title')}</Title>
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
