import { Badge, Group, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** A screen of a later milestone (plan §2 decision 53): its menu item opens this page. */
export function ComingSoonPage({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <Stack gap="sm" maw={720}>
      <Group gap="sm">
        <Title order={1}>{title}</Title>
        <Badge variant="light" color="gray">
          {t('shell.nav.soon')}
        </Badge>
      </Group>
      <Text>{t('comingSoon.text')}</Text>
    </Stack>
  );
}
