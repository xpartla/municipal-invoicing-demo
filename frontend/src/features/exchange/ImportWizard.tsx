import { Alert, Button, Checkbox, Group, Loader, Stack, Stepper, Text } from '@mantine/core';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  isWorking,
  useApply,
  useCancel,
  useDryRun,
  useImport,
  usePreview,
  useSetMapping,
  type ColumnMapping,
  type ImportRun,
  type ImportType,
  type Owner,
  type ReadOptions,
} from './api';
import { splitErrors } from './mapping';
import { MappingStep } from './MappingStep';
import { useProblemText } from './problemText';
import { ReadStep } from './ReadStep';
import { ReportView } from './ReportView';
import { TemplateSave } from './TemplateSave';
import { UploadStep } from './UploadStep';

interface Props {
  owner: Owner;
  runId?: string;
  initialType?: ImportType;
  initialYear?: number;
  /** A new run was uploaded: the page puts its ID in the URL, so a reload continues it. */
  onRun: (runId: string) => void;
  /** Where "done" leads: Číselníky, or the import history. */
  done: React.ReactNode;
}

type Step = 0 | 1 | 2 | 3 | 4;

/** The step a run is at: uploaded → reading, mapped → mapping, a dry run → its report, an
 * apply or the end → done. */
function stepOf(run: ImportRun): Step {
  if (run.state === 'applied' || run.state === 'cancelled') return 4;
  if (run.state === 'dry_run_ok' || run.state === 'dry_run_failed' || run.applying) return 3;
  if (run.state === 'mapped') return run.job_id ? 3 : 2;
  return 1;
}

/** The import wizard (plan §9.2): upload, reading, mapping, the dry run's report, apply,
 * and saving the mapping as a template. Each step is the run's state on the server. */
export function ImportWizard({ owner, runId, initialType, initialYear, onRun, done }: Props) {
  const { t } = useTranslation();
  const run = useImport(owner, runId);
  if (runId === undefined) {
    return (
      <Stack gap="md">
        <Steps active={0} />
        <UploadStep
          owner={owner}
          initialType={initialType}
          initialYear={initialYear}
          onUploaded={(uploaded) => {
            onRun(uploaded.id);
          }}
        />
      </Stack>
    );
  }
  if (!run.data) {
    return run.isError ? (
      <Alert color="red">{t('exchange.wizard.notFound')}</Alert>
    ) : (
      <Loader aria-label={t('common.loading')} />
    );
  }
  return <RunWizard key={run.data.id} owner={owner} run={run.data} done={done} />;
}

function Steps({ active }: { active: Step }) {
  const { t } = useTranslation();
  return (
    <Stepper active={active} size="sm" allowNextStepsSelect={false}>
      {(['upload', 'read', 'map', 'check', 'done'] as const).map((step) => (
        <Stepper.Step key={step} label={t(`exchange.wizard.steps.${step}`)} />
      ))}
    </Stepper>
  );
}

function RunWizard({ owner, run, done }: { owner: Owner; run: ImportRun; done: React.ReactNode }) {
  const { t } = useTranslation();
  const problemText = useProblemText();
  const serverStep = stepOf(run);
  // The step the person went to (back to reading or mapping, on to mapping); null follows
  // the server. A finished run, or one whose job runs, shows the server's step.
  const [chosen, setChosen] = useState<Step | null>(null);
  const working = isWorking(run);
  const step: Step = serverStep === 4 || working ? serverStep : (chosen ?? serverStep);
  const [options, setOptions] = useState<ReadOptions | null>(run.options);
  // The person's mapping; until they change it, the preview's suggestion (the run's own
  // mapping, a template the headers chose, or one from the header names).
  const [edited, setEdited] = useState<{
    mapping: ColumnMapping;
    templateId: string | null;
  } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const preview = usePreview(owner, run.id, options);
  const setRunMapping = useSetMapping(owner, run.id);
  const dryRun = useDryRun(owner, run.id);
  const apply = useApply(owner, run.id);
  const cancel = useCancel(owner, run.id);
  const mapping = edited?.mapping ?? preview.data?.suggestion ?? null;
  const templateId = edited ? edited.templateId : (preview.data?.template_id ?? null);
  const { refreshLists } = apply;

  // An applied run made a new version: Číselníky shows it.
  useEffect(() => {
    if (run.state === 'applied') void refreshLists();
  }, [run.state, refreshLists]);

  const readOptions = (): ReadOptions => ({
    sheet: options?.sheet ?? preview.data?.sheet ?? null,
    header_row: options?.header_row ?? preview.data?.header_row ?? null,
    encoding: options?.encoding ?? (preview.data?.encoding as ReadOptions['encoding']) ?? null,
    delimiter: options?.delimiter ?? (preview.data?.delimiter as ReadOptions['delimiter']) ?? null,
  });

  const startDryRun = async () => {
    if (!mapping) return;
    setProblem(null);
    try {
      await setRunMapping.mutateAsync({ options: readOptions(), mapping, templateId });
      await dryRun.mutateAsync(undefined);
      setConfirmed(false);
      setChosen(null);
    } catch (error) {
      setProblem(problemText(error));
    }
  };

  const startApply = async () => {
    setProblem(null);
    try {
      await apply.mutateAsync(confirmed);
      setChosen(null);
    } catch (error) {
      setProblem(problemText(error));
    }
  };

  const giveUp = async () => {
    try {
      await cancel.mutateAsync(undefined);
    } catch (error) {
      setProblem(problemText(error));
    }
  };

  const { hard, confirmable } = splitErrors(run.report?.errors);
  const canCancel = !run.applying && run.state !== 'applied' && run.state !== 'cancelled';

  return (
    <Stack gap="md">
      <Steps active={step} />
      <Text size="sm" c="dimmed">
        {t('exchange.wizard.runOf', {
          type: t(`exchange.types.${run.import_type}`),
          year: run.year,
          file: run.file.name,
        })}
      </Text>
      {step === 1 &&
        (preview.data ? (
          <ReadStep
            preview={preview.data}
            options={options ?? {}}
            onOptions={(next) => {
              setOptions(next);
              setEdited(null);
            }}
            onNext={() => {
              setChosen(2);
            }}
            loading={preview.isFetching}
          />
        ) : preview.isError ? (
          <Alert color="red">{problemText(preview.error)}</Alert>
        ) : (
          <Loader aria-label={t('common.loading')} />
        ))}
      {step === 2 && preview.data && mapping && (
        <MappingStep
          preview={preview.data}
          mapping={mapping}
          onMapping={(next) => {
            setEdited({ mapping: next, templateId: null });
          }}
          onBack={() => {
            setChosen(1);
          }}
          onDryRun={() => void startDryRun()}
          running={setRunMapping.isPending || dryRun.isPending}
          problem={problem ?? (run.last_error ? t('exchange.wizard.refused') : null)}
        />
      )}
      {step === 3 && (
        <Stack gap="md">
          {working ? (
            <Group gap="sm">
              <Loader size="sm" aria-hidden />
              <Text role="status">
                {run.applying ? t('exchange.wizard.applying') : t('exchange.wizard.checking')}
              </Text>
            </Group>
          ) : !run.report ? (
            <Stack gap="sm" align="flex-start">
              <Alert color="orange" title={t('exchange.wizard.refusedTitle')}>
                {t('exchange.wizard.refused')}
              </Alert>
              <Button
                onClick={() => {
                  setChosen(2);
                }}
              >
                {t('exchange.wizard.backToMapping')}
              </Button>
            </Stack>
          ) : (
            <>
              <ReportView report={run.report} importType={run.import_type} />
              {hard.length > 0 ? (
                <Alert color="red" title={t('exchange.wizard.hardTitle')}>
                  {t('exchange.wizard.hard')}
                </Alert>
              ) : confirmable.length > 0 ? (
                <Checkbox
                  label={t('exchange.wizard.confirm', { count: confirmable.length })}
                  description={t('exchange.wizard.confirmHint')}
                  checked={confirmed}
                  onChange={(event) => {
                    setConfirmed(event.currentTarget.checked);
                  }}
                />
              ) : null}
              {problem && <Alert color="red">{problem}</Alert>}
              <Group>
                <Button
                  variant="default"
                  onClick={() => {
                    setChosen(2);
                  }}
                  disabled={run.applying}
                >
                  {t('exchange.wizard.backToMapping')}
                </Button>
                <Button
                  onClick={() => void startApply()}
                  loading={apply.isPending}
                  disabled={!run.can_apply || (confirmable.length > 0 && !confirmed)}
                >
                  {t('exchange.wizard.apply')}
                </Button>
              </Group>
            </>
          )}
        </Stack>
      )}
      {step === 4 && (
        <Stack gap="md">
          {run.state === 'cancelled' ? (
            <Alert color="gray">{t('exchange.wizard.cancelled')}</Alert>
          ) : (
            <Alert color="green" title={t('exchange.wizard.doneTitle')}>
              {run.import_type === 'past_bookings'
                ? t('exchange.wizard.doneBookings', { count: run.report?.diff?.added ?? 0 })
                : t('exchange.wizard.doneList', {
                    list: t(`exchange.types.${run.import_type}`),
                    count: run.report?.entries ?? 0,
                  })}
            </Alert>
          )}
          {run.state === 'applied' && run.mapping && (
            <TemplateSave owner={owner} run={run} suggestedName={preview.data?.template_name} />
          )}
          <Group>{done}</Group>
        </Stack>
      )}
      {canCancel && step > 0 && step < 4 && (
        <Group>
          <Button
            variant="subtle"
            color="red"
            onClick={() => void giveUp()}
            loading={cancel.isPending}
          >
            {t('exchange.wizard.cancel')}
          </Button>
        </Group>
      )}
    </Stack>
  );
}
