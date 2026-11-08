import { Button, Group, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

import { Dialog } from './Dialog';

/** A yes-or-no question before an action that is hard to undo. */
export function ConfirmDialog({
  opened,
  title,
  message,
  confirmLabel,
  danger = false,
  loading = false,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog opened={opened} onClose={onClose} title={title} centered>
      <Text mb="md">{message}</Text>
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>
          {t('common.cancel')}
        </Button>
        <Button color={danger ? 'red' : undefined} loading={loading} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Group>
    </Dialog>
  );
}
