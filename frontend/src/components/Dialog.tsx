import { Modal, type ModalProps } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** Mantine's modal with a named close button (axe: button-name). */
export function Dialog(props: ModalProps) {
  const { t } = useTranslation();
  return <Modal {...props} closeButtonProps={{ 'aria-label': t('common.close') }} />;
}
