import { ActionIcon, Button, CopyButton, Tooltip } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';

/**
 * Copy buttons for typing into TOPSET (plan §10.4): one value, or a whole line as
 * tab-separated cells. The button says when it has copied.
 */
export function CopyValue({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation();
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? t('invoice.copy.copied') : label} withArrow>
          <ActionIcon
            variant="subtle"
            size="sm"
            color={copied ? 'teal' : 'gray'}
            aria-label={label}
            onClick={copy}
          >
            {copied ? <IconCheck size={14} aria-hidden /> : <IconCopy size={14} aria-hidden />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  );
}

/** `text` is what the button shows (default "Riadok"); it must be part of `label` (axe). */
export function CopyRow({ value, label, text }: { value: string; label: string; text?: string }) {
  const { t } = useTranslation();
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Button
          size="compact-xs"
          variant="default"
          aria-label={label}
          leftSection={
            copied ? <IconCheck size={12} aria-hidden /> : <IconCopy size={12} aria-hidden />
          }
          onClick={copy}
        >
          {copied ? t('invoice.copy.copied') : (text ?? t('invoice.copy.row'))}
        </Button>
      )}
    </CopyButton>
  );
}
