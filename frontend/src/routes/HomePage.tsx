import { Anchor, Paper, Stack, Text, Title } from '@mantine/core';
import { useParams } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { useMe } from '../features/identity/api';

/** Domov of a customer. P2-M7 fills it with the dashboard of plan §10.2. */
export function HomePage() {
  const { t } = useTranslation();
  const { customerId } = useParams({ from: '/_app/c/$customerId' });
  const { data: me } = useMe();
  const name = me?.customers.find((c) => c.id === customerId)?.name ?? '';
  return (
    <Stack gap="md" maw={720}>
      <Title order={1}>{t('home.title')}</Title>
      <Text>{t('home.intro', { name })}</Text>
      <Paper withBorder p="md">
        <Text>{t('home.legacy')}</Text>
        <Anchor href="/index.html">{t('home.legacyLink')}</Anchor>
      </Paper>
    </Stack>
  );
}
