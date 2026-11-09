import { Button, Group, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/** Previous and next page buttons with "page n of m"; nothing for a single page. */
export function Pager({
  page,
  pages,
  onPage,
}: {
  page: number;
  pages: number;
  onPage: (page: number) => void;
}) {
  const { t } = useTranslation();
  if (pages <= 1) return null;
  return (
    <Group gap="sm">
      <Button
        variant="default"
        size="xs"
        disabled={page <= 1}
        onClick={() => {
          onPage(page - 1);
        }}
      >
        {t('common.previous')}
      </Button>
      <Text size="sm">{t('common.page', { page, pages })}</Text>
      <Button
        variant="default"
        size="xs"
        disabled={page >= pages}
        onClick={() => {
          onPage(page + 1);
        }}
      >
        {t('common.next')}
      </Button>
    </Group>
  );
}
