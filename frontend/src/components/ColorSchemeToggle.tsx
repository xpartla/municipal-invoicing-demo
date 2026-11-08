import { ActionIcon, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { IconMoon, IconSun } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

export function ColorSchemeToggle() {
  const { t } = useTranslation();
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme('light', { getInitialValueInEffect: false });
  const next = computed === 'dark' ? 'light' : 'dark';
  const label = next === 'light' ? t('shell.theme.toLight') : t('shell.theme.toDark');
  return (
    <ActionIcon
      variant="default"
      size="lg"
      aria-label={label}
      title={label}
      onClick={() => {
        setColorScheme(next);
      }}
    >
      {next === 'light' ? <IconSun size={18} aria-hidden /> : <IconMoon size={18} aria-hidden />}
    </ActionIcon>
  );
}
