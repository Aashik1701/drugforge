import { describe, it, expect } from 'vitest';
import { validateSmiles } from './chemUtils';

describe('validateSmiles', () => {
  it('accepts a well-formed SMILES string', () => {
    expect(validateSmiles('CCO').valid).toBe(true);
  });

  it('rejects an empty/missing SMILES string', () => {
    expect(validateSmiles('').valid).toBe(false);
    expect(validateSmiles(undefined).valid).toBe(false);
  });

  it('rejects a string that is too short', () => {
    expect(validateSmiles('CC').valid).toBe(false);
  });

  it('rejects unbalanced brackets', () => {
    expect(validateSmiles('CC(O').valid).toBe(false);
  });

  it('rejects invalid characters', () => {
    expect(validateSmiles('CC!O$$$').valid).toBe(false);
  });
});
