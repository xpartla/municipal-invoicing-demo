import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import type { Issue } from './api';
import type { Transform } from './mapping';

/** One line about a field's transforms: "orezať, doplniť nulami na 3". */
export function useTransformSummary() {
  const { t } = useTranslation();
  return useCallback(
    (transforms: readonly Transform[]) =>
      transforms.length === 0
        ? t('exchange.transforms.none')
        : transforms
            .map((transform) => {
              switch (transform.op) {
                case 'zero_pad':
                  return t('exchange.transforms.summary.zero_pad', { width: transform.width });
                case 'split':
                  return t('exchange.transforms.summary.split', {
                    part: transform.index + 1,
                  });
                default:
                  return t(`exchange.transforms.ops.${transform.op}`);
              }
            })
            .join(', '),
    [t],
  );
}

/** The Slovak wording of an issue, by its code; the API's English message otherwise. */
export function useIssueText() {
  const { t } = useTranslation();
  return (issue: Issue) =>
    t(`exchange.issues.${issue.code}` as 'exchange.issues.missing', {
      defaultValue: issue.message,
    });
}
