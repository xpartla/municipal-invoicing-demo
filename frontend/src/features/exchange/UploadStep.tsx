import { Button, FileInput, Group, Select, Stack, Text } from '@mantine/core';
import { IconUpload } from '@tabler/icons-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useUpload, type ImportRun, type ImportType, type Owner } from './api';
import { CUSTOMER_TYPES, GLOBAL_TYPES } from './mapping';
import { useProblemText } from './problemText';

const MAX_MB = 20;

interface Props {
  owner: Owner;
  initialType?: ImportType;
  initialYear?: number;
  onUploaded: (run: ImportRun) => void;
}

/** Step 1: what to import, for which year, and the file (CSV, XLSX or XLS). */
export function UploadStep({ owner, initialType, initialYear, onUploaded }: Props) {
  const { t } = useTranslation();
  const problemText = useProblemText();
  const types = owner === 'global' ? GLOBAL_TYPES : CUSTOMER_TYPES;
  const thisYear = new Date().getFullYear();
  const [importType, setImportType] = useState<ImportType>(
    initialType && types.includes(initialType) ? initialType : (types[0] ?? 'accounts'),
  );
  const [year, setYear] = useState(initialYear ?? thisYear);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const upload = useUpload(owner);
  const years = [thisYear + 1, thisYear, thisYear - 1, thisYear - 2];
  if (!years.includes(year)) years.push(year);

  const submit = async () => {
    setProblem(null);
    if (!file) {
      setProblem(t('exchange.upload.fileRequired'));
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setProblem(t('exchange.upload.tooLarge', { mb: MAX_MB }));
      return;
    }
    try {
      onUploaded(await upload.mutateAsync({ file, importType, year }));
    } catch (error) {
      setProblem(problemText(error));
    }
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <Stack gap="md" maw={560}>
        <Select
          label={t('exchange.upload.type')}
          data={types.map((type) => ({ value: type, label: t(`exchange.types.${type}`) }))}
          value={importType}
          allowDeselect={false}
          onChange={(value) => {
            if (value) setImportType(value);
          }}
        />
        <Text size="sm" c="dimmed">
          {t(`exchange.typeNotes.${importType}`)}
        </Text>
        <Select
          label={t('exchange.upload.year')}
          data={years.sort((a, b) => b - a).map((y) => ({ value: String(y), label: String(y) }))}
          value={String(year)}
          allowDeselect={false}
          onChange={(value) => {
            if (value) setYear(Number(value));
          }}
          w={140}
        />
        <FileInput
          label={t('exchange.upload.file')}
          description={t('exchange.upload.fileHint', { mb: MAX_MB })}
          accept=".csv,.txt,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          value={file}
          onChange={setFile}
          clearable
          error={problem}
          leftSection={<IconUpload size={16} aria-hidden />}
        />
        <Group>
          <Button type="submit" loading={upload.isPending}>
            {t('exchange.upload.submit')}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
