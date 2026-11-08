import { Box, Center, Group, Paper, Stack, Text, Title } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { ColorSchemeToggle } from './ColorSchemeToggle';

/** The frame of the pages before a login: the product mark and one card with a heading. */
export function AuthCard({ title, children }: { title: string; children: React.ReactNode }) {
  const { t } = useTranslation();
  return (
    <Box component="main" mih="100vh" bg="var(--riso-canvas)" px="md" py="xl">
      <Center>
        <Stack w="100%" maw={420} gap="lg">
          <Group justify="space-between">
            <Stack gap={0}>
              <Text fw={700} size="xl">
                {t('app.name')}
              </Text>
              <Text c="dimmed" size="sm">
                {t('app.tagline')}
              </Text>
            </Stack>
            <ColorSchemeToggle />
          </Group>
          <Paper withBorder p="lg" radius="md" bg="var(--riso-surface)">
            <Stack gap="md">
              <Title order={1} size="h2">
                {title}
              </Title>
              {children}
            </Stack>
          </Paper>
        </Stack>
      </Center>
    </Box>
  );
}
