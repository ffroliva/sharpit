import { isPanelAccessError } from './api';

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

function toErrorMessage(error: unknown, fallback = 'Request failed'): string {
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

function isServerUnreachableError(error: unknown): boolean {
  const normalized = toErrorMessage(error, '').trim().toLowerCase();
  let end = normalized.length;
  while (end > 0 && (normalized[end - 1] === '.' || normalized[end - 1] === '!')) end--;
  const message = normalized.slice(0, end);
  return Boolean(message) && (message.startsWith("server unreachable:") || NETWORK_ERROR_MARKERS.some(
    (marker) => message === marker || message.endsWith(`: ${marker}`) || message.includes(` ${marker}`),
  ));
}

export function describeLoadError(error: unknown): string {
  return !isPanelAccessError(error) && isServerUnreachableError(error)
    ? SERVER_UNREACHABLE_MESSAGE
    : toErrorMessage(error);
}
