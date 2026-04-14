import { isString } from '../tsTypeGuards';
import { ErrorStatusCode, LlmProvider } from '../tsTypes';
import { AppError } from '../utils/appError';

export const parseString = (value: unknown, name?: string): string => {
  if (!isString(value) || !value.trim()) {
    throw new AppError({
      message: name
        ? `${name} must be a non-empty string`
        : 'Value must be a non-empty string',
      statusCode: ErrorStatusCode.INTERNAL_SERVER_ERROR,
    });
  }
  return value.trim();
};

export const parseOptionalString = (value: unknown): string | undefined => {
  if (value === undefined || value === null || value === '') return undefined;
  if (!isString(value)) return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
};

export const parseProvider = (value: unknown): LlmProvider => {
  const str = isString(value) ? value.trim().toLowerCase() : '';
  if (str === 'openai' || str === 'google') return str;
  return 'openai';
};

export const parsePort = (value: unknown): number => {
  const n = parseInt(isString(value) ? value : String(value ?? ''), 10);
  return isNaN(n) ? 8050 : n;
};
