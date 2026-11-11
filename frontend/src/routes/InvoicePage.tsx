import {
  Accordion,
  Alert,
  Badge,
  Button,
  Code,
  Grid,
  Group,
  List,
  Loader,
  Paper,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { IconArrowLeft, IconArrowRight, IconFileText } from '@tabler/icons-react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyRow, CopyValue } from '../components/CopyButtons';
import { Dialog } from '../components/Dialog';
import { AnchorLink, ButtonLink } from '../components/RouterLinks';
import { ScrollTable } from '../components/ScrollTable';
import { useMe } from '../features/identity/api';
import { inCustomer } from '../features/identity/capabilities';
import { useExtraction } from '../features/intake/api';
import { CheckStep } from '../features/intake/CheckStep';
import { DocumentViewer, type Highlight } from '../features/intake/DocumentViewer';
import { EInvoiceViewer } from '../features/intake/EInvoiceViewer';
import {
  useBookingPreview,
  useInvoice,
  useInvoiceAction,
  READING,
  useNextInvoice,
  usePickedLine,
  useSeriesCodes,
  useWholeList,
  type BookingInput,
  type Entry,
  type ExportScope,
  type Invoice,
  type Placement,
} from '../features/invoices/api';
import {
  codingOf,
  documentOf,
  linesOf,
  problems as findProblems,
  sameCoding,
  swapped,
  type DocumentFields,
  type Line,
} from '../features/invoices/coding';
import { CorrectionEditor, type EditorLists } from '../features/invoices/CorrectionEditor';
import { engineText, formatPercent } from '../features/invoices/engineText';
import { Evidence } from '../features/invoices/Evidence';
import { ExportDialog } from '../features/invoices/ExportDialog';
import type { FieldPath } from '../features/invoices/FieldsForm';
import { HistoryList } from '../features/invoices/HistoryList';
import { ProposalCards, type Names } from '../features/invoices/ProposalCards';
import type { InvoicePageSearch } from '../features/invoices/search';
import { ApiError } from '../lib/apiError';
import { formatAmount, formatDate } from '../lib/format';
import { useNotify } from '../lib/notify';

const BOOKED = new Set(['booked', 'exported', 'paid']);

function today(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${String(now.getFullYear())}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** A value to show, or a dash for an empty one. */
function shown(value: string | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : value;
}

function describe(entry: Entry): string {
  const values = entry.values as Record<string, unknown>;
  return typeof values.description === 'string' ? values.description : '';
}

/**
 * Faktúra (plan §10.4): the invoice's proposal or booking laid out like TOPSET's tabs with
 * copy buttons, "Iná položka", "Prečo práve toto", the correction editors limited to the
 * code lists, and the actions its state allows; its fields; its history. Everything the
 * demo's proposal page did, on a stored invoice.
 */
export function InvoicePage() {
  const { t } = useTranslation();
  const { customerId, invoiceId } = useParams({
    from: '/_app/c/$customerId/invoices/$invoiceId',
  });
  const found = useInvoice(customerId, invoiceId);
  const invoice = found.data;
  if (found.isPending) return <Loader aria-label={t('common.loading')} />;
  if (!invoice) {
    return (
      <Alert color="red">
        {found.error instanceof ApiError && found.error.status === 404
          ? t('notFound.title')
          : t('common.error')}
      </Alert>
    );
  }
  // A new proposal or booking starts the page's working copy afresh.
  const version = [invoice.id, invoice.state, invoice.coded_at, invoice.booked_at, invoice.number];
  return <InvoiceView key={version.join('|')} customerId={customerId} invoice={invoice} />;
}

function InvoiceView({ customerId, invoice }: { customerId: string; invoice: Invoice }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const search = useSearch({ from: '/_app/c/$customerId/invoices/$invoiceId' });
  const navigate = useNavigate({ from: '/c/$customerId/invoices/$invoiceId' });
  const { data: me } = useMe();
  const canProcess = me ? inCustomer(me, customerId, 'invoices.process') : false;
  const proposal = invoice.proposal;
  const source = invoice.booking?.coding ?? proposal;
  const proposedLines = useMemo(
    () =>
      source && (source.posting ?? []).length
        ? linesOf({ posting: source.posting ?? [], budget: source.budget ?? [] })
        : [],
    [source],
  );
  const [lines, setLines] = useState<Line[]>(proposedLines);
  const [doc, setDoc] = useState<DocumentFields>(() =>
    source ? documentOf(source) : { series: 'FD', number: '', booking_date: '' },
  );
  const [mode, setMode] = useState<'view' | 'correct'>('view');
  const [note, setNote] = useState('');
  const [confirm, setConfirm] = useState<{ booking: BookingInput; placement: Placement } | null>(
    null,
  );
  const [dialog, setDialog] = useState<'unbook' | 'pay' | 'discard' | null>(null);
  const [reason, setReason] = useState('');
  const [paidOn, setPaidOn] = useState(today);
  const [exporting, setExporting] = useState<ExportScope | null>(null);
  const [saveProblems, setSaveProblems] = useState<string[]>([]);

  const action = useInvoiceAction(customerId, invoice.id);
  const preview = useBookingPreview(customerId, invoice.id);
  const picked = usePickedLine(customerId, invoice.id);
  const bookable = canProcess && invoice.actions.includes('book') && proposal !== null;
  const manual = proposal !== null && (proposal.posting ?? []).length === 0;
  const booked = BOOKED.has(invoice.state);
  const year =
    invoice.basis?.year ?? (doc.booking_date ? Number(doc.booking_date.slice(0, 4)) : undefined);
  const positions = useWholeList(customerId, 'budget_expense', year, true);
  const accounts = useWholeList(customerId, 'accounts', year, true);
  const transfers = useWholeList(customerId, 'transfers', year, mode === 'correct');
  const series = useSeriesCodes(customerId, year ?? new Date().getFullYear());
  const next = useNextInvoice(customerId, invoice.id, canProcess);

  const names: Names = useMemo(() => {
    const byKey = (entries: Entry[] | undefined) =>
      new Map((entries ?? []).map((e) => [e.key, describe(e)]));
    const positionNames = byKey(positions.data);
    const accountNames = byKey(accounts.data);
    return {
      position: (key) => positionNames.get(key) ?? '',
      account: (key) => accountNames.get(key) ?? '',
    };
  }, [positions.data, accounts.data]);

  const lists: EditorLists = useMemo(() => {
    const options = (entries: Entry[] | undefined) =>
      (entries ?? []).map((e) => ({ value: e.key, label: `${e.key} · ${describe(e)}` }));
    return {
      positions: options(positions.data),
      accounts: options(accounts.data),
      supplierAccounts: options(accounts.data?.filter((e) => e.key.startsWith('32'))),
      transfers: (transfers.data ?? []).map((e) => {
        const values = e.values as Record<string, unknown>;
        const name = typeof values.name === 'string' ? values.name : '';
        const zdroj = typeof values.zdroj === 'string' ? values.zdroj : '';
        return { value: e.key, label: `${e.key} · ${name}`, zdroj };
      }),
    };
  }, [positions.data, accounts.data, transfers.data]);

  const gross = invoice.fields?.totals.gross ?? null;
  const proposalCoding =
    proposal && (proposal.posting ?? []).length
      ? {
          document: proposal.document,
          posting: proposal.posting ?? [],
          budget: proposal.budget ?? [],
        }
      : null;
  const final = codingOf(doc, lines);
  const changed = proposalCoding === null || !sameCoding(final, proposalCoding);
  const problems =
    mode === 'correct'
      ? findProblems(doc, lines, gross, {
          positions: new Set(lists.positions.map((o) => o.value)),
          accounts: new Set(lists.accounts.map((o) => o.value)),
        })
      : { errors: [], warnings: [] };

  const reset = () => {
    setLines(proposedLines);
    setDoc(source ? documentOf(source) : { series: 'FD', number: '', booking_date: '' });
    setMode('view');
    setNote('');
    setSaveProblems([]);
  };

  const failed = (error: unknown) => {
    if (error instanceof ApiError && error.status === 422 && error.problems.length) {
      setSaveProblems(error.problems.map((p) => engineText(p.msg)));
    } else {
      notify.failure(error);
    }
  };

  const book = async (booking: BookingInput) => {
    try {
      const result = await action.mutateAsync({ action: 'book', booking });
      setConfirm(null);
      notify.success(t('invoice.booking.done', { number: result.invoice.number ?? '' }));
    } catch (error) {
      setConfirm(null);
      failed(error);
    }
  };

  const save = async () => {
    setSaveProblems([]);
    const accepted = proposalCoding !== null && !changed;
    const booking: BookingInput = {
      action: accepted ? 'accepted' : 'corrected',
      coding: accepted ? proposalCoding : final,
      note: note.trim() || null,
    };
    try {
      const placement = await preview.mutateAsync(booking);
      if (placement.moved || placement.shifts.length > 0) setConfirm({ booking, placement });
      else await book(booking);
    } catch (error) {
      failed(error);
    }
  };

  const step = async (
    run: Parameters<typeof action.mutateAsync>[0],
    done: string,
  ): Promise<void> => {
    try {
      await action.mutateAsync(run);
      setDialog(null);
      notify.success(done);
    } catch (error) {
      notify.failure(error);
    }
  };

  const confidence = proposal?.confidence.overall ?? 0;
  const supplier = invoice.fields?.supplier.name ?? t('invoice.unknownSupplier');
  const reasons = [...(proposal?.validation.errors ?? []), ...(proposal?.review_reasons ?? [])];

  // The tab is in the URL; the check step comes first while the fields wait for it.
  const reading = READING.has(invoice.state);
  const failedReading = invoice.state === 'extraction_failed';
  const checkable = canProcess && (reading || failedReading || invoice.actions.includes('check'));
  const tabs: NonNullable<InvoicePageSearch['tab']>[] = [
    ...(checkable ? (['check'] as const) : []),
    'proposal',
    'fields',
    'history',
  ];
  const fresh = reading || failedReading || invoice.state === 'extracted';
  const tab =
    search.tab && tabs.includes(search.tab)
      ? search.tab
      : checkable && fresh
        ? 'check'
        : 'proposal';
  const goTab = (value: string | null) => {
    const next = tabs.find((name) => name === value);
    if (!next) return;
    void navigate({ search: (prev) => ({ ...prev, tab: next }), replace: true });
  };
  const queue = search.queue ? search.queue.split(',') : [];
  const customer = me?.customers.find((c) => c.id === customerId);

  // The document as it was read, beside the tabs: open on the check step, by choice elsewhere.
  const extraction = useExtraction(
    customerId,
    invoice.document_id && !reading && !failedReading ? invoice.document_id : null,
  );
  const [focused, setFocused] = useState<FieldPath | null>(null);
  const [documentChoice, setDocumentChoice] = useState<boolean | null>(null);
  const read = extraction.data;
  const viewerShown = read !== undefined && (documentChoice ?? tab === 'check');
  const readNote = read?.note;
  const highlight: Highlight | null =
    focused === null || !read
      ? null
      : focused.startsWith('handwritten.')
        ? readNote
          ? { page: readNote.page, box: readNote.box }
          : null
        : (read.evidence[focused] ?? null);

  return (
    <Stack gap="md">
      <AnchorLink to="/c/$customerId/invoices" params={{ customerId }} search={{}} size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} aria-hidden />
          {t('invoice.back')}
        </Group>
      </AnchorLink>
      <Group justify="space-between" align="flex-start">
        <Stack gap={2}>
          <Title order={1}>
            {invoice.number
              ? t('invoice.titleNumber', { number: invoice.number })
              : t('invoice.titleNone')}
          </Title>
          <Text c="dimmed">
            {supplier}
            {invoice.fields?.invoice.number ? `, ${invoice.fields.invoice.number}` : ''}
            {gross !== null ? `, ${formatAmount(gross)}` : ''}
          </Text>
        </Stack>
        <Group gap="sm">
          {read && (
            <Button
              variant="default"
              size="xs"
              leftSection={<IconFileText size={14} aria-hidden />}
              aria-pressed={viewerShown}
              onClick={() => {
                setDocumentChoice(!viewerShown);
              }}
            >
              {viewerShown ? t('viewer.hide') : t('viewer.show')}
            </Button>
          )}
          {queue.length > 0 && (
            <Button
              size="xs"
              rightSection={<IconArrowRight size={14} aria-hidden />}
              onClick={() => {
                const [next, ...rest] = queue;
                if (!next) return;
                void navigate({
                  to: '/c/$customerId/invoices/$invoiceId',
                  params: { customerId, invoiceId: next },
                  search: { tab: 'check', queue: rest.length ? rest.join(',') : undefined },
                });
              }}
            >
              {t('check.next', { count: queue.length })}
            </Button>
          )}
          <Badge size="lg">{t(`invoices.states.${invoice.state}`)}</Badge>
        </Group>
      </Group>

      <Grid gap="md">
        {viewerShown && invoice.document_id && (
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <div
              style={{
                position: 'sticky',
                top: 'calc(var(--app-shell-header-height, 0px) + 1rem)',
              }}
            >
              {read.source === 'einvoice' ? (
                <EInvoiceViewer
                  customerId={customerId}
                  documentId={invoice.document_id}
                  pages={read.pages}
                  focused={focused}
                />
              ) : (
                <DocumentViewer
                  customerId={customerId}
                  documentId={invoice.document_id}
                  pages={read.pages}
                  highlight={highlight}
                />
              )}
            </div>
          </Grid.Col>
        )}
        <Grid.Col span={{ base: 12, lg: viewerShown ? 7 : 12 }}>
          <Tabs value={tab} onChange={goTab} keepMounted={false}>
            <Tabs.List>
              {checkable && <Tabs.Tab value="check">{t('invoice.tabs.check')}</Tabs.Tab>}
              <Tabs.Tab value="proposal">{t('invoice.tabs.proposal')}</Tabs.Tab>
              <Tabs.Tab value="fields">{t('invoice.tabs.fields')}</Tabs.Tab>
              <Tabs.Tab value="history">{t('invoice.tabs.history')}</Tabs.Tab>
            </Tabs.List>

            {checkable && customer && (
              <Tabs.Panel value="check" pt="md">
                <CheckStep
                  customerId={customerId}
                  invoice={invoice}
                  extraction={read}
                  customer={{ name: customer.name, ico: customer.ico }}
                  onFieldFocus={setFocused}
                  onDone={async () => {
                    await navigate({
                      search: (prev) => ({ ...prev, tab: 'proposal' }),
                      replace: true,
                    });
                  }}
                />
              </Tabs.Panel>
            )}

            <Tabs.Panel value="proposal" pt="md">
              <Stack gap="md">
                {invoice.coding_error && <Alert color="red">{t('invoice.codingError')}</Alert>}
                {!source && !invoice.coding_error && (
                  <Text c="dimmed">{t('invoice.proposalAfterCheck')}</Text>
                )}
                {source && (
                  <Paper withBorder p="md" radius="md">
                    <Group justify="space-between" align="flex-start" gap="md">
                      <Group gap="xl" align="flex-end">
                        {mode === 'correct' ? (
                          <>
                            <Select
                              label={t('invoice.doc.series')}
                              data={[...new Set([...(series.data ?? []), doc.series])]}
                              value={doc.series}
                              allowDeselect={false}
                              onChange={(value) => {
                                setDoc({ ...doc, series: value ?? doc.series });
                              }}
                              w={110}
                            />
                            <TextInput
                              label={t('invoice.doc.number')}
                              value={doc.number}
                              placeholder="FD/NNN/RR"
                              onChange={(event) => {
                                setDoc({ ...doc, number: event.currentTarget.value.trim() });
                              }}
                              w={150}
                            />
                            <TextInput
                              type="date"
                              label={t('invoice.doc.bookingDate')}
                              value={doc.booking_date}
                              onChange={(event) => {
                                setDoc({ ...doc, booking_date: event.currentTarget.value });
                              }}
                            />
                          </>
                        ) : (
                          <>
                            <Stack gap={0}>
                              <Text size="xs" c="dimmed">
                                {t('invoice.doc.series')}
                              </Text>
                              <Text ff="monospace" fw={700}>
                                {doc.series}
                              </Text>
                            </Stack>
                            <Stack gap={0}>
                              <Text size="xs" c="dimmed">
                                {t('invoice.doc.number')}
                              </Text>
                              <Group gap={4}>
                                <Text ff="monospace" fw={700}>
                                  {doc.number || '—'}
                                </Text>
                                <CopyValue
                                  value={doc.number}
                                  label={t('invoice.copy.what', { what: t('invoice.doc.number') })}
                                />
                              </Group>
                            </Stack>
                            <Stack gap={0}>
                              <Text size="xs" c="dimmed">
                                {t('invoice.doc.bookingDate')}
                              </Text>
                              <Group gap={4}>
                                <Text fw={700}>{formatDate(doc.booking_date)}</Text>
                                <CopyValue
                                  value={formatDate(doc.booking_date).replace(/\u00a0/g, ' ')}
                                  label={t('invoice.copy.what', {
                                    what: t('invoice.doc.bookingDate'),
                                  })}
                                />
                              </Group>
                            </Stack>
                          </>
                        )}
                      </Group>
                      {proposal && !booked && (
                        <Group gap="xs">
                          <Badge
                            color={
                              confidence >= 0.85 ? 'green' : confidence >= 0.75 ? 'yellow' : 'red'
                            }
                          >
                            {t('invoice.badges.confidence', { value: formatPercent(confidence) })}
                          </Badge>
                          <Badge color={proposal.validation.ok ? 'green' : 'red'}>
                            {proposal.validation.ok
                              ? t('invoice.badges.codesOk')
                              : t('invoice.badges.codesBad')}
                          </Badge>
                          <Badge color={proposal.needs_review ? 'yellow' : 'green'}>
                            {proposal.needs_review
                              ? t('invoice.badges.review')
                              : t('invoice.badges.noReview')}
                          </Badge>
                          <Badge color="gray">
                            {proposal.supplier.known
                              ? t('invoice.badges.known')
                              : t('invoice.badges.newSupplier')}
                          </Badge>
                        </Group>
                      )}
                      {invoice.booking && (
                        <Group gap="xs">
                          <Badge color="teal">
                            {t(`invoice.booking.${invoice.booking.action}`)}
                          </Badge>
                          <Text size="sm" c="dimmed">
                            {t('invoice.booking.bookedAs', {
                              date: formatDate(invoice.booked_at?.slice(0, 10)),
                            })}
                          </Text>
                        </Group>
                      )}
                    </Group>
                    {!booked && reasons.length > 0 && (
                      <Alert
                        color={proposal?.validation.errors?.length ? 'red' : 'yellow'}
                        mt="md"
                        title={t('invoice.reasons')}
                      >
                        <List size="sm">
                          {reasons.map((reason) => (
                            <List.Item key={reason}>{engineText(reason)}</List.Item>
                          ))}
                        </List>
                      </Alert>
                    )}
                  </Paper>
                )}

                {manual && mode === 'view' && !booked && (
                  <Paper withBorder p="md" radius="md">
                    <Title order={2} size="h4">
                      {t('invoice.manual.title')}
                    </Title>
                    <Text size="sm" my="xs">
                      {t('invoice.manual.text')}
                    </Text>
                    {bookable && (
                      <Button
                        onClick={() => {
                          setLines([
                            {
                              key: '',
                              md: '',
                              dal: doc.series === 'FDŠJ' ? '321 080' : '321 000',
                              amount: gross === null ? '' : String(gross).replace('.', ','),
                              budgetText: '',
                              postingText: '',
                              transfer: '',
                              choice: '',
                            },
                          ]);
                          setMode('correct');
                        }}
                      >
                        {t('invoice.manual.button')}
                      </Button>
                    )}
                  </Paper>
                )}

                {mode === 'view' && lines.length > 0 && (
                  <ProposalCards
                    lines={lines}
                    names={names}
                    alternatives={bookable && !booked ? (proposal.alternatives ?? []) : null}
                    onSwap={(index, choice) => {
                      const proposed = proposedLines[index];
                      const line = lines[index];
                      if (!proposed || !line) return;
                      const alternative =
                        choice === '' ? null : (proposal?.alternatives?.[Number(choice)] ?? null);
                      setLines(
                        lines.map((l, i) =>
                          i === index ? swapped(line, alternative, proposed, choice) : l,
                        ),
                      );
                    }}
                  />
                )}

                {mode === 'correct' && (
                  <CorrectionEditor
                    lines={lines}
                    onLines={setLines}
                    onPicked={(index, key) => {
                      picked.mutate(key, {
                        onSuccess: (derived) => {
                          setLines((current) =>
                            current.map((line, i) =>
                              i === index && line.key === key
                                ? {
                                    ...line,
                                    md: derived.md ?? line.md,
                                    dal: derived.dal ?? line.dal,
                                    transfer: derived.transfer ?? '',
                                    budgetText: derived.budget_text ?? line.budgetText,
                                    postingText: derived.posting_text ?? line.postingText,
                                  }
                                : line,
                            ),
                          );
                        },
                        onError: notify.failure,
                      });
                    }}
                    lists={lists}
                    gross={gross}
                    problems={problems}
                    note={note}
                    onNote={setNote}
                  />
                )}

                {saveProblems.length > 0 && (
                  <Alert color="red">
                    <List size="sm">
                      {saveProblems.map((problem, i) => (
                        <List.Item key={i}>{problem}</List.Item>
                      ))}
                    </List>
                  </Alert>
                )}

                {canProcess && (
                  <Group gap="xs">
                    {bookable && mode === 'view' && !manual && (
                      <>
                        <Button
                          loading={preview.isPending || action.isPending}
                          onClick={() => void save()}
                        >
                          {changed
                            ? t('invoice.actions.acceptChanged')
                            : t('invoice.actions.accept')}
                        </Button>
                        <Button
                          variant="default"
                          onClick={() => {
                            setMode('correct');
                          }}
                        >
                          {t('invoice.actions.correct')}
                        </Button>
                        {changed && (
                          <Button variant="subtle" onClick={reset}>
                            {t('invoice.actions.original')}
                          </Button>
                        )}
                      </>
                    )}
                    {mode === 'correct' && (
                      <>
                        <Button
                          disabled={problems.errors.length > 0}
                          loading={preview.isPending || action.isPending}
                          onClick={() => void save()}
                        >
                          {t('invoice.correct.save')}
                        </Button>
                        <Button variant="default" onClick={reset}>
                          {t('common.cancel')}
                        </Button>
                      </>
                    )}
                    {mode === 'view' && invoice.actions.includes('recode') && (
                      <Button
                        variant="default"
                        loading={action.isPending}
                        onClick={() => void step({ action: 'recode' }, t('invoice.recoded'))}
                      >
                        {t('invoice.actions.recode')}
                      </Button>
                    )}
                    {invoice.actions.includes('pay') && (
                      <Button
                        variant="default"
                        onClick={() => {
                          setPaidOn(today());
                          setDialog('pay');
                        }}
                      >
                        {t('invoice.actions.pay')}
                      </Button>
                    )}
                    {booked && (
                      <Button
                        variant="default"
                        onClick={() => {
                          setExporting({ invoiceIds: [invoice.id] });
                        }}
                      >
                        {t('invoice.actions.export')}
                      </Button>
                    )}
                    {invoice.actions.includes('unbook') && (
                      <Button
                        variant="default"
                        color="red"
                        onClick={() => {
                          setReason('');
                          setDialog('unbook');
                        }}
                      >
                        {t('invoice.actions.unbook')}
                      </Button>
                    )}
                    {invoice.actions.includes('discard') && mode === 'view' && (
                      <Button
                        variant="subtle"
                        color="red"
                        onClick={() => {
                          setReason('');
                          setDialog('discard');
                        }}
                      >
                        {t('invoice.actions.discard')}
                      </Button>
                    )}
                    {next.data && (
                      <ButtonLink
                        variant="light"
                        to="/c/$customerId/invoices/$invoiceId"
                        params={{ customerId, invoiceId: next.data }}
                        rightSection={<IconArrowRight size={16} aria-hidden />}
                      >
                        {t('invoice.actions.next')}
                      </ButtonLink>
                    )}
                  </Group>
                )}

                {proposal && !booked && <Evidence proposal={proposal} />}
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="fields" pt="md">
              <InvoiceFields invoice={invoice} />
            </Tabs.Panel>

            <Tabs.Panel value="history" pt="md">
              <HistoryList customerId={customerId} invoiceId={invoice.id} />
            </Tabs.Panel>
          </Tabs>
        </Grid.Col>
      </Grid>

      <Dialog
        opened={confirm !== null}
        onClose={() => {
          setConfirm(null);
        }}
        title={t('invoice.booking.title')}
      >
        {confirm && (
          <Stack gap="sm">
            <Text>
              {confirm.placement.moved
                ? t('invoice.booking.moved', {
                    requested: confirm.placement.requested ?? '',
                    number: confirm.placement.number,
                  })
                : t('invoice.booking.gets', { number: confirm.placement.number })}
            </Text>
            {confirm.placement.shifts.length > 0 && (
              <>
                <Text size="sm">{t('invoice.booking.shifts')}</Text>
                <List size="sm">
                  {confirm.placement.shifts.map((shift) => (
                    <List.Item key={shift.old}>
                      <Code>{shift.old}</Code> → <Code>{shift.new}</Code>
                      {shift.invoice_id === null ? '' : ''}
                    </List.Item>
                  ))}
                </List>
              </>
            )}
            <Group justify="flex-end">
              <Button
                variant="default"
                onClick={() => {
                  setConfirm(null);
                }}
              >
                {t('common.cancel')}
              </Button>
              <Button loading={action.isPending} onClick={() => void book(confirm.booking)}>
                {t('invoice.booking.confirm')}
              </Button>
            </Group>
          </Stack>
        )}
      </Dialog>

      <Dialog
        opened={dialog !== null}
        onClose={() => {
          setDialog(null);
        }}
        title={dialog ? t(`invoice.actions.${dialog}`) : ''}
      >
        <Stack gap="md">
          {dialog === 'pay' && (
            <>
              <Text size="sm">{t('invoice.pay.text')}</Text>
              <TextInput
                type="date"
                required
                label={t('invoice.pay.paidOn')}
                value={paidOn}
                onChange={(event) => {
                  setPaidOn(event.currentTarget.value);
                }}
              />
            </>
          )}
          {(dialog === 'unbook' || dialog === 'discard') && (
            <>
              <Text size="sm">{t(`invoice.${dialog}.text`)}</Text>
              <TextInput
                label={t(`invoice.${dialog}.reason`)}
                value={reason}
                maxLength={500}
                onChange={(event) => {
                  setReason(event.currentTarget.value);
                }}
              />
            </>
          )}
          <Group justify="flex-end">
            <Button
              variant="default"
              onClick={() => {
                setDialog(null);
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              color={dialog === 'pay' ? undefined : 'red'}
              disabled={dialog === 'pay' && !paidOn}
              loading={action.isPending}
              onClick={() => {
                if (dialog === 'pay') void step({ action: 'pay', paidOn }, t('invoice.pay.done'));
                if (dialog === 'unbook')
                  void step(
                    { action: 'unbook', reason: reason.trim() || undefined },
                    t('invoice.unbook.done'),
                  );
                if (dialog === 'discard')
                  void step(
                    { action: 'discard', reason: reason.trim() || undefined },
                    t('invoice.discard.done'),
                  );
              }}
            >
              {dialog ? t(`invoice.actions.${dialog}`) : ''}
            </Button>
          </Group>
        </Stack>
      </Dialog>

      <ExportDialog
        customerId={customerId}
        scope={exporting}
        onClose={() => {
          setExporting(null);
        }}
      />
    </Stack>
  );
}

/** Údaje faktúry: the fields as checked, and the document as the OCR or the entry gave it. */
function InvoiceFields({ invoice }: { invoice: Invoice }) {
  const { t } = useTranslation();
  const fields = invoice.fields;
  if (!fields) return <Text c="dimmed">—</Text>;
  const json = JSON.stringify(fields, null, 2);
  const rows: [string, string | null | undefined][] = [
    [t('invoice.fields.supplier'), fields.supplier.name],
    [t('invoice.fields.ico'), fields.supplier.ico],
    [t('invoice.fields.number'), fields.invoice.number],
    [t('invoice.fields.vs'), fields.invoice.variable_symbol],
    [t('invoice.fields.issued'), formatDate(fields.invoice.issue_date)],
    [t('invoice.fields.supplied'), formatDate(fields.invoice.delivery_date)],
    [t('invoice.fields.due'), formatDate(fields.invoice.due_date)],
    [t('invoice.fields.net'), formatAmount(fields.totals.net)],
    [t('invoice.fields.vat'), formatAmount(fields.totals.vat)],
    [t('invoice.fields.gross'), formatAmount(fields.totals.gross)],
    [t('invoice.fields.handwrittenDate'), formatDate(fields.handwritten.date)],
    [t('invoice.fields.handwrittenNumber'), fields.handwritten.number],
    [t('invoice.fields.source'), t(`invoices.channels.${invoice.channel}`)],
  ];
  return (
    <Stack gap="md">
      <Table withRowBorders={false} verticalSpacing={4} maw={560}>
        <Table.Tbody>
          {rows.map(([label, value]) => (
            <Table.Tr key={label}>
              <Table.Th scope="row" w={220} fw={500}>
                {label}
              </Table.Th>
              <Table.Td>{shown(value)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      {(fields.lines ?? []).length > 0 && (
        <ScrollTable label={t('invoice.fields.lines')} minWidth={420}>
          <Table striped verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">{t('invoice.fields.line')}</Table.Th>
                <Table.Th scope="col" style={{ textAlign: 'right' }}>
                  {t('invoice.fields.lineGross')}
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(fields.lines ?? []).map((line, i) => (
                <Table.Tr key={i}>
                  <Table.Td>{line.description}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>{formatAmount(line.gross)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollTable>
      )}
      <Accordion variant="contained">
        <Accordion.Item value="json">
          <Accordion.Control>
            <Title order={2} size="h5">
              {t('invoice.ocrJson')}
            </Title>
          </Accordion.Control>
          <Accordion.Panel>
            <Group justify="space-between" mb="xs">
              <Text size="sm" c="dimmed">
                {t('invoice.ocrJsonText')}
              </Text>
              <CopyRow value={json} label={t('invoice.copyJson')} text={t('invoice.copyJson')} />
            </Group>
            <Code block tabIndex={0} aria-label={t('invoice.ocrJson')}>
              {json}
            </Code>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}
