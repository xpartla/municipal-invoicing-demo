import { Anchor, Box, Button, Group, Stack, Text, Title } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { useContext } from 'react';
import { useTranslation } from 'react-i18next';

import { InShellContext } from '../components/inShell';

/**
 * What a crash of a screen shows instead of a blank page. Inside the shell (the router's
 * default error component) the navbar stays, so the other screens remain a click away; a
 * crash of the shell itself or of a page before the login shows it alone, as the `main`.
 */
export function ErrorPage() {
  const { t } = useTranslation();
  const inShell = useContext(InShellContext);
  const content = (
    <Stack gap="sm" maw={720}>
      <Title order={1}>{t('errorPage.title')}</Title>
      <Text>{t('errorPage.text')}</Text>
      <Group gap="md">
        <Button
          leftSection={<IconRefresh size={16} aria-hidden />}
          onClick={() => {
            window.location.reload();
          }}
        >
          {t('errorPage.reload')}
        </Button>
        <Anchor href="/">{t('errorPage.home')}</Anchor>
      </Group>
    </Stack>
  );
  return inShell ? (
    content
  ) : (
    <Box component="main" p="md">
      {content}
    </Box>
  );
}
