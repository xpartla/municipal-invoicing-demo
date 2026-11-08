import { Anchor, Stack, Text, Title } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

export function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <Stack gap="sm">
      <Title order={1}>{t('forbidden.title')}</Title>
      <Text>{t('forbidden.text')}</Text>
      <Anchor component={Link} to="/">
        {t('forbidden.home')}
      </Anchor>
    </Stack>
  );
}
