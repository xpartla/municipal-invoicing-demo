import { Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** Správy: a placeholder in phase 2 (plan §10.7, decision 40). */
export function MessagesPage() {
  const { t } = useTranslation();
  return (
    <Stack gap="sm" maw={720}>
      <Title order={1}>{t('shell.nav.messages')}</Title>
      <Text>{t('messages.text')}</Text>
    </Stack>
  );
}
