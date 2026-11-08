import { Anchor, Box, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** What a crash of a screen shows instead of a blank page. */
export function ErrorPage() {
  const { t } = useTranslation();
  return (
    <Box component="main" p="md">
      <Stack gap="sm">
        <Title order={1}>{t('errorPage.title')}</Title>
        <Text>{t('errorPage.text')}</Text>
        <Anchor href="/">{t('errorPage.home')}</Anchor>
      </Stack>
    </Box>
  );
}
