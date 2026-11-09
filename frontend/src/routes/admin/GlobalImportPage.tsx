import { Stack, Title } from '@mantine/core';
import { useNavigate, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AnchorLink, ButtonLink } from '../../components/RouterLinks';
import { ImportWizard } from '../../features/exchange/ImportWizard';

/** A global list's import (plan §10.9): EK, COFOG, funding sources and the framework chart,
 * per year, as the admin. */
export function GlobalImportPage() {
  const { t } = useTranslation();
  const search = useSearch({ from: '/_app/admin/codelists/import' });
  const navigate = useNavigate();
  return (
    <Stack gap="md">
      <Title order={1}>{t('exchange.wizard.globalTitle')}</Title>
      <AnchorLink to="/admin/codelists" size="sm">
        {t('exchange.wizard.toGlobal')}
      </AnchorLink>
      <ImportWizard
        owner="global"
        runId={search.run}
        initialType={search.type}
        initialYear={search.year}
        onRun={(run) => {
          void navigate({ to: '/admin/codelists/import', search: { run } });
        }}
        done={<ButtonLink to="/admin/codelists">{t('exchange.wizard.toGlobal')}</ButtonLink>}
      />
    </Stack>
  );
}
