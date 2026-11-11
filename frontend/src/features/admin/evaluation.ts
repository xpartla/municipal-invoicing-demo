import { useQuery } from '@tanstack/react-query';

import { api, type Schemas } from '../../api/client';
import { unwrap } from '../../lib/apiError';

/** Vyhodnotenie (plan §10.9): the evaluation report, admins only (decision 67). */

export type EvalReport = Schemas['EvalReport'];
export type Split = EvalReport['split'];

export const SPLITS = ['heldout', 'seed', 'anchor'] as const satisfies readonly Split[];

/** The per-group columns, as on the M3 page. */
export const GROUP_COLUMNS = [
  'correct',
  'full_key',
  'ek',
  'md',
  'review_rate',
  'silent_errors',
] as const;

export const CASE_FILTERS = ['wrong', 'silent', 'review', 'all'] as const;
export type CaseFilter = (typeof CASE_FILTERS)[number];

/** `refresh` > 0 runs the evaluation again instead of reading the latest report. */
export function useEvaluation(split: Split, refresh: number) {
  return useQuery({
    queryKey: ['evaluation', split, refresh],
    queryFn: () =>
      unwrap(api.GET('/api/admin/eval', { params: { query: { split, refresh: refresh > 0 } } })),
    staleTime: Infinity,
  });
}

export function casesOf(report: EvalReport, filter: CaseFilter): EvalReport['cases'] {
  switch (filter) {
    case 'wrong':
      return report.cases.filter((c) => !c.correct);
    case 'silent':
      return report.cases.filter((c) => !c.correct && !c.needs_review);
    case 'review':
      return report.cases.filter((c) => c.needs_review);
    case 'all':
      return report.cases;
  }
}
