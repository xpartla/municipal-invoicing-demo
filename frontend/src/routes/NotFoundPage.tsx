import { Anchor, Stack, Text, Title } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <Stack gap="sm">
      <Title order={1}>{t('notFound.title')}</Title>
      <Text>{t('notFound.text')}</Text>
      <Anchor component={Link} to="/">
        {t('notFound.home')}
      </Anchor>
    </Stack>
  );
}
