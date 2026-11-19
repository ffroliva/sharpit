import { isPanelAccessError } from './api';

const SERVER_UNREACHABLE_TITLE = 'Server unreachable';
const SERVER_UNREACHABLE_MESSAGE =
  'sharpit could not reach the application. The server may have been stopped. Start it again, then retry or refresh this page.';

const NETWORK_ERROR_MARKERS = [
  'failed to fetch',
  'fetch failed',
  'load failed',
  'network request failed',
  'networkerror when attempting to fetch resource',
  'the network connection was lost',
];

export interface LoadErrorDescription {
  title: string;
  message: string;
  serverUnreachable: boolean;
}

export function toErrorMessage(error: unknown, fallback = 'Request failed'): string {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  if (
    error &&
    typeof error === 'object' &&
    typeof (error as Record<string, unknown>).message === 'string' &&
    ((error as Record<string, unknown>).message as string).trim()
  ) {
    return (error as Record<string, unknown>).message as string;
  }
  return fallback;
}

export function isAbortError(error: unknown): boolean {
  return error !== null && typeof error === 'object' && (error as Record<string, unknown>).name === 'AbortError';
}

export function isServerUnreachableError(error: unknown): boolean {
  const normalized = toErrorMessage(error, '').trim().toLowerCase();
  let end = normalized.length;
  while (end > 0 && (normalized[end - 1] === '.' || normalized[end - 1] === '!')) {
    end--;
  }
  const message = normalized.slice(0, end);
  if (!message) return false;
  if (message.startsWith(`${SERVER_UNREACHABLE_TITLE.toLowerCase()}:`)) return true;

  return NETWORK_ERROR_MARKERS.some(
    (marker) => message === marker || message.endsWith(`: ${marker}`) || message.includes(` ${marker}`),
  );
}

export function describeLoadError(error: unknown, context: string | null = null): LoadErrorDescription {
  const message = toErrorMessage(error);
  const serverUnreachable = !isPanelAccessError(error) && isServerUnreachableError(message);

  if (serverUnreachable) {
    return {
      title: SERVER_UNREACHABLE_TITLE,
      message: SERVER_UNREACHABLE_MESSAGE,
      serverUnreachable: true,
    };
  }

  return {
    title: 'Load failed',
    message: context ? `${context}: ${message}` : message,
    serverUnreachable: false,
  };
}

export function formatLoadErrorDescription(description: LoadErrorDescription | null | undefined): string {
  if (!description) return '';
  return description.serverUnreachable ? `${description.title}: ${description.message}` : description.message;
}

export function formatLoadError(error: unknown, context: string | null = null): string {
  return formatLoadErrorDescription(describeLoadError(error, context));
}
