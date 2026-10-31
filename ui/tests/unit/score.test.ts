// Ported from BootUI bootui-ui/src/main/frontend/src/utils/scannerScore.test.js; each case cites its source test.
// Not ported: the githubSecurityScore cases (sharpit has no GitHub panel). scoreBandTone maps BootUI's 'secondary'
// to sharpit's 'muted' class.
import { describe, expect, it } from 'vitest';
import { advisorAssessment, overallScore, scoreBandTone, scoreFromSeverityCounts } from '../../src/lib/score';

const report = (overrides: Record<string, unknown> = {}): Record<string, any> => ({
  scan: { status: 'SCANNED' },
  severityCounts: [],
  evidence: { usable: true, coverageComplete: true, limitations: [] },
  ...overrides,
});
const evidence = (overrides: Record<string, unknown> = {}) => ({ ...report().evidence, ...overrides });

// ported: scannerScore.test.js "does not color an invalid score %s"
it.each([null, undefined, NaN, Infinity, -1, 101, '80'])('does not color an invalid score %s', (score) => {
  expect(scoreBandTone(score)).toBe('muted');
});

describe('overallScore', () => {
  // ported: scannerScore.test.js overallScore "rounds the simple mean without replacing absent or invalid scores"
  it('rounds the simple mean without replacing absent or invalid scores', () => {
    expect(overallScore([91, 80])).toBe(86);
    expect(overallScore([91, 100, null, undefined, NaN, Infinity, -1, 101, '100'])).toBe(96);
    expect(overallScore([0, 100])).toBe(50);
    expect(
      overallScore([advisorAssessment(report({ scan: { status: 'PARTIAL' }, severityCounts: [{ severity: 'MEDIUM', count: 3 }] })).score]),
    ).toBe(91);
  });

  // ported: scannerScore.test.js overallScore "leaves an unscored collection unscored: %j"
  it.each([undefined, null, [], [null, NaN, '0']])('leaves an unscored collection unscored: %j', (scores) => {
    expect(overallScore(scores)).toBeNull();
  });
});

describe('advisorAssessment', () => {
  // ported: scannerScore.test.js advisorAssessment "uses only explicit backend eligibility for %s, before dismissal"
  it.each(['SCANNED', 'PARTIAL'])('uses only explicit backend eligibility for %s, before dismissal', (status) => {
    const assessment = report({
      scan: { status },
      evidence: evidence({ usable: true }),
      severityCounts: [
        { severity: 'CRITICAL', count: 1 },
        { severity: 'HIGH', count: 2 },
        { severity: 'MEDIUM', count: 3 },
        { severity: 'LOW', count: 4 },
        { severity: 'INFO', count: 7 },
      ],
    });
    expect(advisorAssessment(assessment)).toMatchObject({ score: 42, partial: status === 'PARTIAL' });
    assessment.severityCounts = [];
    expect(advisorAssessment(assessment)).toMatchObject({ score: 100, partial: status === 'PARTIAL' });
    assessment.severityCounts = [{ severity: 'MEDIUM', count: 3 }];
    expect(advisorAssessment(assessment).score).toBe(91);
  });

  // ported: scannerScore.test.js advisorAssessment "keeps coverage independent of score, including zero and confirmed empty scope"
  it('keeps coverage independent of score, including zero and confirmed empty scope', () => {
    expect(advisorAssessment(report({ severityCounts: [{ severity: 'CRITICAL', count: 5 }] }))).toMatchObject({ score: 0, incomplete: false });
    expect(advisorAssessment(report({ evidence: evidence({ usable: false }) }))).toMatchObject({
      score: null, incomplete: false, label: 'Not applicable',
    });
    expect(advisorAssessment(report({ evidence: evidence({ coverageComplete: false }) }))).toMatchObject({
      score: 100, incomplete: true, label: 'Results available',
    });
  });

  // ported: scannerScore.test.js advisorAssessment "never scores %s even with retained findings"
  it.each(['ERROR', 'DISABLED', 'NOT_SCANNED', undefined, 'UNRECOGNIZED'])('never scores %s even with retained findings', (status) => {
    expect(advisorAssessment(report({ scan: { status }, severityCounts: [{ severity: 'HIGH', count: 1 }] }))).toMatchObject({
      score: null, incomplete: false,
    });
  });

  // ported: scannerScore.test.js advisorAssessment "does not reconstruct eligibility from legacy %s"
  it.each(['results', 'findings', 'dependencies'])('does not reconstruct eligibility from legacy %s', (field) => {
    const legacy = report({
      evidence: undefined,
      [field]: [{ id: 'known-rule', status: 'VIOLATION', severity: 'HIGH', vulnerabilities: [{ severity: 'HIGH' }] }],
      severityCounts: [{ severity: 'HIGH', count: 1 }],
      rulesEvaluated: 100,
      checksRun: 100,
    });
    expect(advisorAssessment(legacy, { vulnerabilities: field === 'dependencies' })).toMatchObject({
      score: null, incomplete: true, label: 'Not scored', invalid: false,
    });
    expect(advisorAssessment(legacy).reason).toContain('coverage is unknown');
    legacy.evidence = evidence({ usable: false, coverageComplete: false });
    expect(advisorAssessment(legacy).score).toBeNull();
  });

  // ported: scannerScore.test.js advisorAssessment "uses the same aggregate evidence for dependency and other advisors, without inspecting details"
  it('uses the same aggregate evidence for dependency and other advisors, without inspecting details', () => {
    const dependencyReport = report({
      evidence: evidence({ usable: true, coverageComplete: false, limitations: ['Findings with unknown severity are excluded from score penalties.'] }),
      severityCounts: [
        { severity: 'HIGH', count: 1 },
        { severity: 'UNKNOWN', count: 1 },
        { severity: 'NONE', count: 2 },
      ],
    });
    expect(advisorAssessment(dependencyReport, { vulnerabilities: true })).toMatchObject({ score: 90, partial: true });
    dependencyReport.severityCounts = [];
    expect(advisorAssessment(dependencyReport, { vulnerabilities: true })).toMatchObject({ score: 100, partial: true });
    dependencyReport.evidence.usable = false;
    expect(advisorAssessment(dependencyReport, { vulnerabilities: true })).toMatchObject({ score: null, incomplete: true, label: 'Not scored' });
    dependencyReport.evidence.usable = true;
    expect(advisorAssessment(dependencyReport, { vulnerabilities: true })).toMatchObject({ score: 100, partial: true });
  });

  // ported: scannerScore.test.js advisorAssessment "distinguishes genuine INFO from informational limitations without rule identifiers"
  it('distinguishes genuine INFO from informational limitations without rule identifiers', () => {
    const info = report({ evidence: evidence({ usable: false, coverageComplete: false }), severityCounts: [{ severity: 'INFO', count: 1 }] });
    expect(advisorAssessment(info).score).toBeNull();
    info.evidence.usable = true;
    expect(advisorAssessment(info)).toMatchObject({ score: 100, partial: true });
  });

  // ported: scannerScore.test.js advisorAssessment "rejects malformed generic severity summary %j"
  it.each([
    null,
    undefined,
    {},
    ['java.util.List', []],
    [null],
    [{ severity: 'BOGUS', count: 1 }],
    ...[-1, null, '1', NaN, Infinity].map((count) => [{ severity: 'HIGH', count }]),
    [{ severity: 'UNKNOWN', count: 0 }],
    [{ severity: 'NONE', count: 1 }],
  ])('rejects malformed generic severity summary %j', (severityCounts) => {
    expect(advisorAssessment(report({ severityCounts }))).toMatchObject({ score: null, invalid: true });
  });

  // ported: scannerScore.test.js advisorAssessment "rejects malformed explicit evidence %j even with retained findings"
  it.each([
    null,
    [],
    {},
    ...[undefined, null, 0, 1, 'true', 'false', [], {}].map((usable) => evidence({ usable })),
    evidence({ coverageComplete: 'true' }),
    evidence({ limitations: [null] }),
    evidence({ limitations: 'failed' }),
  ])('rejects malformed explicit evidence %j even with retained findings', (invalidEvidence) => {
    expect(advisorAssessment(report({ evidence: invalidEvidence, severityCounts: [{ severity: 'HIGH', count: 1 }] }))).toMatchObject({
      score: null, invalid: true,
    });
  });

  // ported: scannerScore.test.js advisorAssessment "keeps backend limitations and scan details, without claiming whole-application completeness"
  it('keeps backend limitations and scan details, without claiming whole-application completeness', () => {
    const result = advisorAssessment(
      report({ scan: { status: 'PARTIAL', message: 'Entity discovery failed.' }, evidence: evidence({ limitations: ['Schema unavailable.'] }) }),
    );
    expect(result.reason).toContain('Entity discovery failed.');
    expect(result.reason).toContain('Schema unavailable.');
    expect(advisorAssessment(report())).toMatchObject({ label: 'Results available', reason: '', incomplete: false, partial: false });
  });

  // ported: scannerScore.test.js advisorAssessment "preserves score 91 with scan notes for %s evidence"
  it.each(['SCANNED', 'PARTIAL'])('preserves score 91 with scan notes for %s evidence', (status) => {
    expect(
      advisorAssessment(
        report({
          scan: { status },
          severityCounts: [{ severity: 'MEDIUM', count: 3 }],
          evidence: evidence({ coverageComplete: false, limitations: ['Metadata unavailable.'] }),
        }),
      ),
    ).toMatchObject({ score: 91, label: 'Results available', reason: 'Metadata unavailable.', incomplete: true, partial: true, invalid: false });
  });
});

describe('scannerScore', () => {
  // ported: scannerScore.test.js scannerScore "applies the fixed 25/10/3/1/0 penalties and clamps the result"
  it('applies the fixed 25/10/3/1/0 penalties and clamps the result', () => {
    expect(scoreFromSeverityCounts([])).toBe(100);
    expect(scoreFromSeverityCounts([{ severity: 'MEDIUM', count: 3 }])).toBe(91);
    expect(scoreFromSeverityCounts([{ severity: 'CRITICAL', count: 10 }])).toBe(0);
    expect(scoreFromSeverityCounts([{ severity: 'high', count: 1 }])).toBe(90);
    expect(scoreFromSeverityCounts([{ severity: 'UNKNOWN', count: 5 }])).toBe(100);
  });
});
