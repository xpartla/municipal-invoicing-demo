import {
  ActionIcon,
  Button,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { IconArrowDown, IconArrowUp, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Dialog } from '../../components/Dialog';
import {
  newTransform,
  textToValues,
  TRANSFORM_OPS,
  valuesToText,
  type Transform,
  type TransformOp,
} from './mapping';

interface Props {
  field: string;
  transforms: readonly Transform[];
  onSave: (transforms: Transform[]) => void;
  onClose: () => void;
}

/** The field's transforms, applied in order: add, change, move and remove them. */
export function TransformDialog({ field, transforms, onSave, onClose }: Props) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Transform[]>([...transforms]);
  const [adding, setAdding] = useState<TransformOp>('trim');
  const replace = (index: number, next: Transform) => {
    setItems(items.map((item, i) => (i === index ? next : item)));
  };
  const move = (index: number, by: number) => {
    const next = [...items];
    const [item] = next.splice(index, 1);
    if (item) next.splice(index + by, 0, item);
    setItems(next);
  };

  return (
    <Dialog opened onClose={onClose} title={t('exchange.transforms.title', { field })} size="lg">
      <Stack gap="sm">
        <Text size="sm">{t('exchange.transforms.intro')}</Text>
        {items.length === 0 && (
          <Text size="sm" c="dimmed">
            {t('exchange.transforms.none')}
          </Text>
        )}
        {items.map((item, index) => {
          const name = t(`exchange.transforms.ops.${item.op}`);
          return (
            <Paper key={index} withBorder p="sm">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Stack gap="xs" style={{ flex: 1 }}>
                  <Text fw={500}>
                    {index + 1}. {name}
                  </Text>
                  <TransformFields
                    transform={item}
                    onChange={(next) => {
                      replace(index, next);
                    }}
                  />
                </Stack>
                <Group gap={4} wrap="nowrap">
                  <ActionIcon
                    variant="subtle"
                    aria-label={t('exchange.transforms.up', { name })}
                    disabled={index === 0}
                    onClick={() => {
                      move(index, -1);
                    }}
                  >
                    <IconArrowUp size={16} aria-hidden />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    aria-label={t('exchange.transforms.down', { name })}
                    disabled={index === items.length - 1}
                    onClick={() => {
                      move(index, 1);
                    }}
                  >
                    <IconArrowDown size={16} aria-hidden />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label={t('exchange.transforms.remove', { name })}
                    onClick={() => {
                      setItems(items.filter((_, i) => i !== index));
                    }}
                  >
                    <IconTrash size={16} aria-hidden />
                  </ActionIcon>
                </Group>
              </Group>
            </Paper>
          );
        })}
        <Group align="flex-end">
          <Select
            label={t('exchange.transforms.add')}
            data={TRANSFORM_OPS.map((op) => ({
              value: op,
              label: t(`exchange.transforms.ops.${op}`),
            }))}
            value={adding}
            allowDeselect={false}
            onChange={(value) => {
              if (value) setAdding(value);
            }}
          />
          <Button
            variant="default"
            onClick={() => {
              setItems([...items, newTransform(adding)]);
            }}
          >
            {t('exchange.transforms.addButton')}
          </Button>
        </Group>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => {
              onSave(items);
            }}
          >
            {t('common.save')}
          </Button>
        </Group>
      </Stack>
    </Dialog>
  );
}

function TransformFields({
  transform,
  onChange,
}: {
  transform: Transform;
  onChange: (next: Transform) => void;
}) {
  const { t } = useTranslation();
  switch (transform.op) {
    case 'trim':
      return (
        <Text size="sm" c="dimmed">
          {t('exchange.transforms.hints.trim')}
        </Text>
      );
    case 'zero_pad':
      return (
        <NumberInput
          label={t('exchange.transforms.width')}
          min={1}
          max={12}
          value={transform.width}
          onChange={(value) => {
            if (typeof value === 'number') onChange({ ...transform, width: value });
          }}
          w={160}
        />
      );
    case 'split':
      return (
        <Group gap="sm" wrap="wrap">
          <TextInput
            label={t('exchange.transforms.separator')}
            description={t('exchange.transforms.separatorHint')}
            value={transform.separator}
            onChange={(event) => {
              onChange({ ...transform, separator: event.currentTarget.value });
            }}
            w={200}
          />
          <NumberInput
            label={t('exchange.transforms.part')}
            min={1}
            max={20}
            value={transform.index + 1}
            onChange={(value) => {
              if (typeof value === 'number') onChange({ ...transform, index: value - 1 });
            }}
            w={120}
          />
          <NumberInput
            label={t('exchange.transforms.count')}
            description={t('exchange.transforms.countHint')}
            min={1}
            max={20}
            value={transform.count ?? ''}
            onChange={(value) => {
              onChange({ ...transform, count: typeof value === 'number' ? value : null });
            }}
            w={200}
          />
        </Group>
      );
    case 'decimal':
      return (
        <Select
          label={t('exchange.transforms.decimalSeparator')}
          data={(['auto', ',', '.'] as const).map((value) => ({
            value,
            label: t(
              `exchange.transforms.decimalSeparators.${value === 'auto' ? 'auto' : value === ',' ? 'comma' : 'point'}`,
            ),
          }))}
          value={transform.separator}
          allowDeselect={false}
          onChange={(value) => {
            if (value) onChange({ ...transform, separator: value });
          }}
          w={240}
        />
      );
    case 'date':
      return (
        <TextInput
          label={t('exchange.transforms.formats')}
          description={t('exchange.transforms.formatsHint')}
          value={transform.formats.join(', ')}
          onChange={(event) => {
            const formats = event.currentTarget.value
              .split(',')
              .map((f) => f.trim())
              .filter(Boolean);
            onChange({ ...transform, formats });
          }}
        />
      );
    case 'map':
      return (
        <Stack gap="xs">
          <Textarea
            label={t('exchange.transforms.values')}
            description={t('exchange.transforms.valuesHint')}
            autosize
            minRows={3}
            defaultValue={valuesToText(transform.values)}
            onBlur={(event) => {
              onChange({ ...transform, values: textToValues(event.currentTarget.value) });
            }}
          />
          <Select
            label={t('exchange.transforms.otherwise')}
            data={(['keep', 'empty', 'error'] as const).map((value) => ({
              value,
              label: t(`exchange.transforms.otherwiseOptions.${value}`),
            }))}
            value={transform.otherwise}
            allowDeselect={false}
            onChange={(value) => {
              if (value) onChange({ ...transform, otherwise: value });
            }}
            w={280}
          />
        </Stack>
      );
  }
}
