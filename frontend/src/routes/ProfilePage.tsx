import { Stack, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { useMe } from '../features/identity/api';
import { currentCustomerId } from '../features/identity/capabilities';
import {
  EmailSection,
  ImpersonationNote,
  PasswordSection,
  PersonalSection,
  SessionsSection,
} from '../features/identity/ProfileSections';
import { CustomerProfile } from '../features/tenancy/CustomerProfile';

/** Profil (plan §5.5, §10.7): the personal sections, then the customer's. */
export function ProfilePage() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  if (!me) return null;
  return (
    <Stack gap="md" maw={760}>
      <Title order={1}>{t('profile.title')}</Title>
      <ImpersonationNote me={me} />
      <PersonalSection me={me} />
      <EmailSection me={me} />
      <PasswordSection me={me} />
      <SessionsSection me={me} />
      {me.customers.length > 0 && (
        <CustomerProfile me={me} initial={currentCustomerId(me, undefined)} />
      )}
    </Stack>
  );
}
