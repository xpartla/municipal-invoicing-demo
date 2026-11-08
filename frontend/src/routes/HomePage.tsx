import { Anchor, Paper, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** Domov. P2-M7 fills it with the customer dashboard of plan §10.2. */
export function HomePage() {
  const { t } = useTranslation();
  return (
    <Stack gap="md" maw={720}>
      <Title order={1}>{t('home.title')}</Title>
      <Text>{t('home.intro')}</Text>
      <Paper withBorder p="md">
        <Text>{t('home.legacy')}</Text>
        <Anchor href="/index.html">{t('home.legacyLink')}</Anchor>
      </Paper>
    </Stack>
  );
}
