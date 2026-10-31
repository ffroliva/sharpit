// Port of BootUI bootui-ui/src/main/frontend/src/utils/scannerScore.js (advisor score and eligibility) and the one
// helper it imports from scanStatus.js. The GitHub score is not ported: sharpit has no GitHub panel.

/** Each active finding subtracts a fixed number of points from a perfect score of 100. */
const SEVERITY_WEIGHTS: Record<string, number> = { CRITICAL: 25, HIGH: 10, MEDIUM: 3, LOW: 1, INFO: 0 };
const MAX_SCORE = 100;
const MIN_SCORE = 0;

export interface SeverityCount { severity: string; count: number }
export interface Evidence { usable: boolean; coverageComplete: boolean; limitations: string[] }
export interface Assessment {
  score: number | null;
  partial: boolean;
  incomplete: boolean;
  label: string;
  reason: string;
  invalid: boolean;
}

const SCAN_STATUS_LABELS: Record<string, string> = {
  NOT_SCANNED: 'Not scanned yet',
  SCANNED: 'Scan complete',
  PARTIAL: 'Incomplete',
  ERROR: 'Scan failed',
  DISABLED: 'Scan disabled',
};

export function scanStatusLabel(status: unknown): string {
  if (!status) return 'Unknown';
  const text = String(status);
  return (
    SCAN_STATUS_LABELS[text] ??
    text.toLowerCase().split('_').filter(Boolean).map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  );
}

/** BootUI's colour band; sharpit's classes are ok / warn / danger / muted (DESIGN.md). */
export function scoreBandTone(score: unknown): 'ok' | 'warn' | 'danger' | 'muted' {
  if (typeof score !== 'number' || !Number.isFinite(score) || score < MIN_SCORE || score > MAX_SCORE) return 'muted';
  return score >= 80 ? 'ok' : score >= 50 ? 'warn' : 'danger';
}

/** Eligibility is established by each report, never by substituting a default number. */
export function overallScore(scores: unknown): number | null {
  const valid = (Array.isArray(scores) ? scores : []).filter(
    (s): s is number => typeof s === 'number' && Number.isFinite(s) && s >= MIN_SCORE && s <= MAX_SCORE,
  );
  return valid.length ? Math.round(valid.reduce((sum, s) => sum + s, 0) / valid.length) : null;
}

function severityWeight(severity: unknown): number {
  if (!severity) return 0;
  return SEVERITY_WEIGHTS[String(severity).toUpperCase()] ?? 0;
}

function isKnownSeverity(severity: unknown): boolean {
  return typeof severity === 'string' && Object.hasOwn(SEVERITY_WEIGHTS, severity.toUpperCase());
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

function isValidEvidence(evidence: unknown): evidence is Evidence {
  return (
    isRecord(evidence) &&
    typeof evidence.usable === 'boolean' &&
    typeof evidence.coverageComplete === 'boolean' &&
    Array.isArray(evidence.limitations) &&
    evidence.limitations.every((r) => typeof r === 'string')
  );
}

export function isValidSeveritySummary(counts: unknown, { vulnerabilities = false } = {}): counts is SeverityCount[] {
  return (
    Array.isArray(counts) &&
    !counts.some(
      (entry: unknown) =>
        !isRecord(entry) ||
        !(
          isKnownSeverity(entry.severity) ||
          (vulnerabilities && typeof entry.severity === 'string' && ['UNKNOWN', 'NONE'].includes(entry.severity.toUpperCase()))
        ) ||
        typeof entry.count !== 'number' ||
        !Number.isFinite(entry.count) ||
        entry.count < 0,
    )
  );
}

/** A 0-100 score from `{severity, count}` entries. */
export function scoreFromSeverityCounts(severityCounts: unknown): number {
  if (!Array.isArray(severityCounts)) return MAX_SCORE;
  const penalty = severityCounts.reduce((total: number, entry: unknown) => {
    const e = isRecord(entry) ? entry : {};
    return total + severityWeight(e.severity) * (Number(e.count) || 0);
  }, 0);
  return clampScore(MAX_SCORE - penalty);
}

function clampScore(value: number): number {
  if (!Number.isFinite(value)) return MIN_SCORE;
  return Math.max(MIN_SCORE, Math.min(MAX_SCORE, Math.round(value)));
}

/** `report` comes straight off the wire, so every field is checked before use. */
export function advisorAssessment(report: any, { vulnerabilities = false } = {}): Assessment {
  const status = report?.scan?.status;
  const unscored = (label: string, reason: string, invalid = false, incomplete = false): Assessment => ({
    score: null, partial: false, incomplete, label, reason, invalid,
  });
  const message = typeof report?.scan?.message === 'string' ? report.scan.message.trim() : '';
  const withDetails = (reason: string) => (message ? `${reason} ${message}` : reason);
  if (!['SCANNED', 'PARTIAL'].includes(status)) {
    return unscored(
      'Not scored',
      withDetails(
        status === 'NOT_SCANNED'
          ? 'Run a scan to calculate a score.'
          : `${scanStatusLabel(status)}. Usable scan evidence is required to calculate a score.`,
      ),
    );
  }
  const counts = report?.severityCounts;
  if (!isValidSeveritySummary(counts, { vulnerabilities })) {
    return unscored('Not scored', 'Scanner returned an invalid severity summary.', true);
  }
  const evidence = report.evidence;
  if (evidence === undefined) {
    return unscored('Not scored', 'Assessment coverage is unknown: completion evidence is unavailable.', false, true);
  }
  if (!isValidEvidence(evidence)) {
    return unscored('Not scored', 'Scanner returned invalid assessment evidence.', true);
  }
  const reasons: string[] = [...evidence.limitations.filter((r) => r.trim())];
  if ((status === 'PARTIAL' || !evidence.coverageComplete) && message) reasons.push(message);
  if ((status === 'PARTIAL' || !evidence.coverageComplete) && !reasons.length) {
    reasons.push('Some applicable checks lack complete evidence.');
  }
  // Coverage and score eligibility are independent: confirmed empty scope is complete but unscored.
  const incomplete = reasons.length > 0;
  if (!evidence.usable) {
    if (!incomplete) {
      return unscored(
        'Not applicable',
        'No applicable checks or observed findings within this scanner’s scope. No score is calculated.',
      );
    }
    return unscored(
      'Not scored',
      ['No usable assessment evidence. Skipped, failed, or unknown-only results cannot establish a score.', ...reasons].join(' '),
      false,
      incomplete,
    );
  }
  const partial = reasons.length > 0;
  return {
    score: scoreFromSeverityCounts(counts),
    partial,
    incomplete,
    label: 'Results available',
    reason: partial ? [...new Set(reasons)].join(' ') : '',
    invalid: false,
  };
}
