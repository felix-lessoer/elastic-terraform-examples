export type PlanAction = 'create' | 'update' | 'replace' | 'delete' | 'read';

export interface PlanResource {
  address: string;
  module: string;
  type: string;
  name: string;
  action: PlanAction;
  label: string;
}

export interface PlanSummary {
  generatedAt?: string;
  resources: PlanResource[];
  counts: Record<PlanAction, number>;
}

export function summarizeTerraformPlan(input: unknown): PlanSummary {
  const plan = input as { timestamp?: unknown; resource_changes?: unknown };
  const counts: Record<PlanAction, number> = {
    create: 0,
    update: 0,
    replace: 0,
    delete: 0,
    read: 0,
  };
  const resources: PlanResource[] = [];
  for (const item of Array.isArray(plan.resource_changes)
    ? plan.resource_changes
    : []) {
    if (!item || typeof item !== 'object') continue;
    const change = item as {
      address?: unknown;
      module_address?: unknown;
      mode?: unknown;
      type?: unknown;
      name?: unknown;
      change?: { actions?: unknown };
    };
    if (
      change.mode !== 'managed' ||
      typeof change.address !== 'string' ||
      typeof change.type !== 'string' ||
      typeof change.name !== 'string' ||
      !Array.isArray(change.change?.actions)
    ) {
      continue;
    }
    const actions = change.change.actions;
    const action: PlanAction | undefined =
      actions.includes('create') && actions.includes('delete')
        ? 'replace'
        : actions.includes('create')
          ? 'create'
          : actions.includes('update')
            ? 'update'
            : actions.includes('delete')
              ? 'delete'
              : actions.includes('read')
                ? 'read'
                : undefined;
    if (!action) continue;
    counts[action] += 1;
    resources.push({
      address: change.address,
      module:
        typeof change.module_address === 'string'
          ? change.module_address
          : 'root',
      type: change.type,
      name: change.name,
      action,
      label: `${action === 'replace' ? 'Replace' : `${action[0].toUpperCase()}${action.slice(1)}`} ${change.type}.${change.name}`,
    });
  }
  resources.sort(
    (left, right) =>
      left.action.localeCompare(right.action) ||
      left.address.localeCompare(right.address),
  );
  return {
    generatedAt:
      typeof plan.timestamp === 'string' ? plan.timestamp : undefined,
    resources,
    counts,
  };
}
