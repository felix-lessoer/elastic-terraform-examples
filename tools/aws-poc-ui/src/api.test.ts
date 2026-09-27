import { describe, expect, it } from 'vitest';
import { normalizeVisibilityExpansionStatus } from './api';

describe('visibility API compatibility', () => {
  it('normalizes responses from an older running server', () => {
    const status = normalizeVisibilityExpansionStatus({
      options: [
        {
          id: 'aws.lambda.function:logs',
          title: 'Collect Lambda logs',
          signal: 'logs',
          resourceType: 'aws.lambda.function',
          affectedResources: 1,
          recommendedCanary: {
            id: 'proposal',
            resource_arn: 'arn:aws:lambda:eu-west-1:123:function:test',
            resource_name: 'test',
            resource_type: 'aws.lambda.function',
            signal: 'logs',
            priority: 1,
            change_summary: 'Collect logs',
            prerequisites: [],
            cost_dimensions: [],
            validation: [],
            rollback: [],
          },
        },
      ],
      selectedProposalIds: [],
      approvals: {},
    } as never);

    expect(status.deployedProposalIds).toEqual([]);
    expect(status.options[0].adapter.available).toBe(false);
    expect(status.options[0].adapter.label).toContain('Restart');
    expect(status.options[0].candidates).toHaveLength(1);
    expect(status.options[0].candidates[0].id).toBe('proposal');
  });
});
