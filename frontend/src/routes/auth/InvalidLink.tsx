import { Anchor, Text } from '@mantine/core';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { AuthCard } from '../../components/AuthCard';

export function InvalidLink() {
  const { t } = useTranslation();
  return (
    <AuthCard title={t('auth.invalidLink.title')}>
      <Text>{t('auth.invalidLink.text')}</Text>
      <Anchor component={Link} to="/login">
        {t('auth.invalidLink.login')}
      </Anchor>
    </AuthCard>
  );
}
