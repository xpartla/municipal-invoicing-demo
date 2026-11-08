import {
  Anchor,
  Box,
  Button,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ScrollTable } from '../../components/ScrollTable';

import { Dialog } from '../../components/Dialog';

import { LinkedText } from '../../components/LinkedText';
import { useOutbox, useOutboxMessage } from '../../features/admin/api';
import { formatDateTime } from '../../lib/format';

const SIZE = 25;

/** Odoslané e-maily (plan §5.3, §10.9): the outbox, newest first, with each message's text.
 * Mail is not sent in phase 2; the links in it work from here. */
export function OutboxPage() {
  const { t } = useTranslation();
  const [to, setTo] = useState('');
  const [debounced] = useDebouncedValue(to, 250);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | undefined>();
  const outbox = useOutbox(page, SIZE, debounced.trim());
  const pages = Math.max(1, Math.ceil((outbox.data?.total ?? 0) / SIZE));
  return (
    <Stack gap="md">
      <Title order={1}>{t('outbox.title')}</Title>
      <Text>{t('outbox.intro')}</Text>
      <TextInput
        label={t('outbox.filter')}
        leftSection={<IconSearch size={16} aria-hidden />}
        value={to}
        onChange={(event) => {
          setTo(event.currentTarget.value);
          setPage(1);
        }}
        w={320}
        maw="100%"
      />
      {outbox.isPending ? (
        <Loader aria-label={t('common.loading')} />
      ) : outbox.data?.items.length ? (
        <ScrollTable label={t('outbox.title')} minWidth={640}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('outbox.created')}</Table.Th>
                <Table.Th>{t('outbox.to')}</Table.Th>
                <Table.Th>{t('outbox.subject')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {outbox.data.items.map((item) => (
                <Table.Tr key={item.id}>
                  <Table.Td>{formatDateTime(item.created_at)}</Table.Td>
                  <Table.Td>{item.to_address}</Table.Td>
                  <Table.Td>
                    <Anchor
                      component="button"
                      type="button"
                      onClick={() => {
                        setOpen(item.id);
                      }}
                    >
                      {item.subject}
                    </Anchor>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      ) : (
        <Text>{t('outbox.none')}</Text>
      )}
      {pages > 1 && (
        <Group gap="sm">
          <Button
            variant="default"
            size="xs"
            disabled={page <= 1}
            onClick={() => {
              setPage(page - 1);
            }}
          >
            {t('outbox.previous')}
          </Button>
          <Text size="sm">{t('outbox.page', { page, pages })}</Text>
          <Button
            variant="default"
            size="xs"
            disabled={page >= pages}
            onClick={() => {
              setPage(page + 1);
            }}
          >
            {t('outbox.next')}
          </Button>
        </Group>
      )}
      <MessageDialog
        messageId={open}
        onClose={() => {
          setOpen(undefined);
        }}
      />
    </Stack>
  );
}

function MessageDialog({
  messageId,
  onClose,
}: {
  messageId: string | undefined;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const message = useOutboxMessage(messageId);
  return (
    <Dialog
      opened={messageId !== undefined}
      onClose={onClose}
      title={t('outbox.message')}
      size="lg"
    >
      {message.data ? (
        <Stack gap="xs">
          <Text size="sm">
            <strong>{t('outbox.to')}:</strong> {message.data.to_address}
          </Text>
          <Text size="sm">
            <strong>{t('outbox.subject')}:</strong> {message.data.subject}
          </Text>
          <Text size="sm" c="dimmed">
            {formatDateTime(message.data.created_at)} · {t('outbox.template')}:{' '}
            {message.data.template}
          </Text>
          <Box
            component="pre"
            p="sm"
            bg="var(--riso-canvas)"
            style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'inherit' }}
          >
            <LinkedText text={message.data.body} />
          </Box>
        </Stack>
      ) : (
        <Loader aria-label={t('common.loading')} />
      )}
    </Dialog>
  );
}
