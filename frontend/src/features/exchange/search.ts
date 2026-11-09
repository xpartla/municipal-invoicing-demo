import type { ImportType } from './api';
import { CUSTOMER_TYPES, GLOBAL_TYPES } from './mapping';

export interface ImportSearch {
  /** The run being continued. */
  run?: string;
  /** The import type and year to start with (from Číselníky). */
  type?: ImportType;
  year?: number;
}

function importSearch(types: readonly ImportType[]) {
  return (search: Record<string, unknown>): ImportSearch => {
    const year = Number(search.year);
    const type = typeof search.type === 'string' ? (search.type as ImportType) : undefined;
    return {
      run: typeof search.run === 'string' && search.run ? search.run : undefined,
      type: type && types.includes(type) ? type : undefined,
      year: Number.isInteger(year) && year >= 2000 && year <= 2100 ? year : undefined,
    };
  };
}

export const customerImportSearch = importSearch(CUSTOMER_TYPES);
export const globalImportSearch = importSearch(GLOBAL_TYPES);
