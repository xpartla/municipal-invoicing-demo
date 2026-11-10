import { describe, expect, it } from 'vitest';

import { checkName, engineText } from './engineText';

// The engine's messages in Slovak (P2-M4-T08): the catalogue's patterns with their argument
// conversions. That every message the dataset produces has a pattern is checked in Python
// (tests/test_engine_messages.py), where the engine runs.

describe('engineText', () => {
  it('translates a message by its pattern, converting the arguments', () => {
    expect(engineText('FD/144/26 is already used')).toBe('číslo FD/144/26 je už použité');
    expect(
      engineText('the entries add up to 93.71, the invoice total is 100.5').replace(/\u00a0/g, ' '),
    ).toBe('položky dávajú spolu 93,71 €, faktúra uvádza spolu 100,50 €');
    expect(engineText('ek confidence is 0.6')).toMatch(/^istota pre .+ je 60 %$/);
    expect(engineText("the supplier IČO '123' fails its check digit")).toMatch(
      /^IČO .+ ‚123‘ nemá platnú kontrolnú číslicu$/,
    );
  });

  it('leaves a message without a pattern as it is', () => {
    expect(engineText('something new the catalogue does not know')).toBe(
      'something new the catalogue does not know',
    );
    expect(engineText(null)).toBe('');
  });

  it('names the checks', () => {
    expect(checkName('no-such-check')).toBe('no-such-check');
  });
});
