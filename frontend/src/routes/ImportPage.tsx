import { Stack, Title } from '@mantine/core';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AnchorLink, ButtonLink } from '../components/RouterLinks';
import { ImportWizard } from '../features/exchange/ImportWizard';
import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { ForbiddenPage } from './ForbiddenPage';

/** Nový import (plan §9.2): the wizard for one of the customer's lists or its past bookings.
 * `?run=` continues a run; `?type=&year=` starts with a list chosen on Číselníky. */
export function ImportPage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const search = useSearch({ from: '/_app/c/$customerId/exchange/import' });
  const navigate = useNavigate();
  const { data: me } = useMe();
  if (me && !inCustomer(me, customerId, 'codelists.edit')) return <ForbiddenPage />;
  return (
    <Stack gap="md">
      <Title order={1}>{t('exchange.wizard.title')}</Title>
      <AnchorLink to="/c/$customerId/exchange" params={{ customerId }} size="sm">
        {t('exchange.wizard.toHistory')}
      </AnchorLink>
      <ImportWizard
        owner={{ customerId }}
        runId={search.run}
        initialType={search.type}
        initialYear={search.year}
        onRun={(run) => {
          void navigate({
            to: '/c/$customerId/exchange/import',
            params: { customerId },
            search: { run },
          });
        }}
        done={
          <>
            <ButtonLink to="/c/$customerId/codelists" params={{ customerId }} search={{}}>
              {t('exchange.wizard.toCodelists')}
            </ButtonLink>
            <ButtonLink
              variant="default"
              to="/c/$customerId/exchange/import"
              params={{ customerId }}
              search={{}}
            >
              {t('exchange.wizard.another')}
            </ButtonLink>
          </>
        }
      />
    </Stack>
  );
}
