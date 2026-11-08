import { Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** A login without any customer, provider or platform role (all its memberships deactivated). */
export function NoAccessPage() {
  const { t } = useTranslation();
  return (
    <Stack gap="sm" maw={720}>
      <Title order={1}>{t('noAccess.title')}</Title>
      <Text>{t('noAccess.text')}</Text>
    </Stack>
  );
}
