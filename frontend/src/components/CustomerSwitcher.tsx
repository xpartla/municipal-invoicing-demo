import { Select } from '@mantine/core';
import { IconBuildingCommunity } from '@tabler/icons-react';
import { useRouter, useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import type { Me } from '../features/identity/api';

/**
 * "Klient: Obec Boldog ▾" with search (plan §10.1, §5.4), for anyone who can open more than one
 * customer. Choosing one keeps the screen: from /c/A/invoices to /c/B/invoices.
 */
export function CustomerSwitcher({
  me,
  customerId,
  onChosen,
}: {
  me: Me;
  customerId: string | undefined;
  onChosen?: () => void;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  return (
    <Select
      label={t('shell.customer.label')}
      placeholder={t('shell.customer.placeholder')}
      nothingFoundMessage={t('shell.customer.nothingFound')}
      data={me.customers.map((c) => ({ value: c.id, label: c.name }))}
      value={customerId ?? null}
      searchable
      allowDeselect={false}
      leftSection={<IconBuildingCommunity size={16} aria-hidden />}
      comboboxProps={{ withinPortal: true }}
      onChange={(value) => {
        if (!value || value === customerId) return;
        const rest = customerId ? pathname.replace(`/c/${customerId}`, '') : '';
        router.history.push(`/c/${value}${rest}`);
        onChosen?.();
      }}
    />
  );
}
