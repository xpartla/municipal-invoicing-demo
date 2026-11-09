import { Group, Select, Stack, Tabs, Text, Title } from '@mantine/core';
import { useParams } from '@tanstack/react-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useListsOverview } from '../features/codelists/api';
import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { ConventionsEditor } from '../features/system/ConventionsEditor';
import { HealthView } from '../features/system/HealthView';
import { ParametersForm } from '../features/system/ParametersForm';

type Tab = 'parameters' | 'conventions' | 'series' | 'health';

/**
 * Systém (plan §10.7): the customer's parameters, its coding conventions and the knowledge
 * health report for a year. The number series join in P2-M4. Users, staff and admins edit;
 * viewers read.
 */
export function SystemPage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [tab, setTab] = useState<Tab>('parameters');
  const overview = useListsOverview(customerId, year);
  const canEdit = me ? inCustomer(me, customerId, 'codelists.edit') : false;
  const years = [...new Set([...(overview.data?.years ?? []), thisYear, thisYear + 1])].sort(
    (a, b) => b - a,
  );
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={1}>{t('system.title')}</Title>
        <Select
          label={t('codelists.year')}
          data={years.map((y) => ({ value: String(y), label: String(y) }))}
          value={String(year)}
          allowDeselect={false}
          onChange={(value) => {
            if (value) setYear(Number(value));
          }}
          w={110}
        />
      </Group>
      <Tabs
        value={tab}
        onChange={(value) => {
          if (value) setTab(value as Tab);
        }}
        keepMounted={false}
      >
        <Tabs.List>
          <Tabs.Tab value="parameters">{t('system.tabs.parameters')}</Tabs.Tab>
          <Tabs.Tab value="conventions">{t('system.tabs.conventions')}</Tabs.Tab>
          <Tabs.Tab value="series">{t('system.tabs.series')}</Tabs.Tab>
          <Tabs.Tab value="health">{t('system.tabs.health')}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="parameters" pt="md">
          <ParametersForm customerId={customerId} year={year} canEdit={canEdit} />
        </Tabs.Panel>
        <Tabs.Panel value="conventions" pt="md">
          <ConventionsEditor customerId={customerId} year={year} canEdit={canEdit} />
        </Tabs.Panel>
        <Tabs.Panel value="series" pt="md">
          <Text>{t('system.series.soon')}</Text>
        </Tabs.Panel>
        <Tabs.Panel value="health" pt="md">
          <HealthView
            customerId={customerId}
            year={year}
            onConventions={() => {
              setTab('conventions');
            }}
          />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
