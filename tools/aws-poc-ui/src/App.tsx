import { useEffect, useMemo, useState } from 'react';
import {
  EuiBadge,
  EuiBasicTable,
  EuiButton,
  EuiButtonEmpty,
  EuiCallOut,
  EuiCheckbox,
  EuiCodeBlock,
  EuiConfirmModal,
  EuiFieldPassword,
  EuiFieldText,
  EuiFlexGroup,
  EuiFlexItem,
  EuiForm,
  EuiFormRow,
  EuiHeader,
  EuiHeaderLogo,
  EuiHeaderSectionItem,
  EuiHealth,
  EuiHorizontalRule,
  EuiLink,
  EuiLoadingSpinner,
  EuiPageTemplate,
  EuiPanel,
  EuiProgress,
  EuiSelect,
  EuiSpacer,
  EuiStat,
  EuiSteps,
  EuiSwitch,
  EuiText,
  EuiTitle,
  type Criteria,
  type EuiBasicTableColumn,
} from '@elastic/eui';
import {
  api,
  type Bootstrap,
  type BrownfieldStatus,
  type CredentialsInput,
  type CredentialsStatus,
  type DeploymentConfig,
  type DeploymentStatus,
  type PlannedResource,
  type PlanSummary,
  type PreflightCheck,
  type RunRecord,
  type VisibilityExpansionStatus,
} from './api';

type AsyncState = 'idle' | 'loading' | 'ready' | 'error';

function ElapsedTime({
  startedAt,
  finishedAt,
}: {
  startedAt: string;
  finishedAt?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (finishedAt) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [finishedAt]);
  const elapsedSeconds = Math.max(
    0,
    Math.floor(
      ((finishedAt ? Date.parse(finishedAt) : now) - Date.parse(startedAt)) /
        1_000,
    ),
  );
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return <>{minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`}</>;
}

function DiscoveryRegionProgress({ logs }: { logs: string[] }) {
  const totalMatch = logs
    .map((line) => line.match(/Scanning (\d+) enabled AWS regions/))
    .find((match) => match);
  const total = totalMatch ? Number(totalMatch[1]) : 0;
  const completed = logs.filter((line) => /^\[[^\]]+\] Complete:/.test(line))
    .length;
  if (!total) return null;
  return (
    <>
      <EuiProgress
        value={Math.min(completed, total)}
        max={total}
        color="primary"
        size="m"
      />
      <EuiSpacer size="xs" />
      <EuiText size="xs" color="subdued">
        <p>
          {completed} of {total} regions complete
        </p>
      </EuiText>
    </>
  );
}

function CredentialsForm({
  status,
  onSaved,
}: {
  status: CredentialsStatus;
  onSaved: (status: CredentialsStatus) => void;
}) {
  const [input, setInput] = useState<CredentialsInput>({
    elasticCloudApiKey: '',
    awsMode: status.aws.mode === 'accessKeys' ? 'accessKeys' : 'profile',
    awsProfile: '',
    awsAccessKeyId: '',
    awsSecretAccessKey: '',
    awsSessionToken: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();

  const update = <Key extends keyof CredentialsInput>(
    key: Key,
    value: CredentialsInput[Key],
  ) => setInput((current) => ({ ...current, [key]: value }));

  const save = async () => {
    setSaving(true);
    setError(undefined);
    try {
      const nextStatus = await api.saveCredentials(input);
      setInput((current) => ({
        ...current,
        elasticCloudApiKey: '',
        awsProfile: '',
        awsAccessKeyId: '',
        awsSecretAccessKey: '',
        awsSessionToken: '',
      }));
      onSaved(nextStatus);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EuiForm component="form">
      <EuiCallOut
        color="warning"
        iconType="lock"
        title="Stored locally on this workstation"
      >
        <p>
          Saved values are written to <code>{status.path}</code> with owner-only
          permissions. The API never returns saved credential values.
        </p>
      </EuiCallOut>
      <EuiSpacer size="m" />
      {error && (
        <>
          <EuiCallOut color="danger" title={error} />
          <EuiSpacer size="m" />
        </>
      )}
      <EuiFlexGroup>
        <EuiFlexItem>
          <EuiFormRow
            label="Elastic Cloud API key"
            helpText={
              status.elasticCloudApiKey.configured
                ? `Already configured${status.elasticCloudApiKey.saved ? ' and saved' : ' in the server environment'}. Leave empty to keep it.`
                : 'Required to create the Elastic project.'
            }
          >
            <EuiFieldPassword
              type="dual"
              value={input.elasticCloudApiKey}
              autoComplete="new-password"
              onChange={(event) =>
                update('elasticCloudApiKey', event.target.value)
              }
            />
          </EuiFormRow>
        </EuiFlexItem>
        <EuiFlexItem>
          <EuiFormRow label="AWS credential method">
            <EuiSelect
              value={input.awsMode}
              options={[
                { value: 'profile', text: 'AWS shared profile' },
                { value: 'accessKeys', text: 'Access keys / session credentials' },
              ]}
              onChange={(event) =>
                update(
                  'awsMode',
                  event.target.value as CredentialsInput['awsMode'],
                )
              }
            />
          </EuiFormRow>
        </EuiFlexItem>
      </EuiFlexGroup>
      {input.awsMode === 'profile' ? (
        <EuiFormRow
          label="AWS profile"
          helpText={
            status.aws.mode === 'profile'
              ? `A profile is already configured${status.aws.saved ? ' and saved' : ''}. Leave empty to keep it.`
              : 'The profile must exist in the workstation AWS configuration.'
          }
        >
          <EuiFieldText
            value={input.awsProfile}
            placeholder="customer-poc"
            onChange={(event) => update('awsProfile', event.target.value)}
          />
        </EuiFormRow>
      ) : (
        <EuiFlexGroup>
          <EuiFlexItem>
            <EuiFormRow
              label="AWS access key ID"
              helpText={
                status.aws.mode === 'accessKeys'
                  ? `Access keys are already configured${status.aws.saved ? ' and saved' : ''}. Leave both key fields empty to keep them.`
                  : undefined
              }
            >
              <EuiFieldPassword
                type="dual"
                value={input.awsAccessKeyId}
                autoComplete="new-password"
                onChange={(event) =>
                  update('awsAccessKeyId', event.target.value)
                }
              />
            </EuiFormRow>
          </EuiFlexItem>
          <EuiFlexItem>
            <EuiFormRow label="AWS secret access key">
              <EuiFieldPassword
                type="dual"
                value={input.awsSecretAccessKey}
                autoComplete="new-password"
                onChange={(event) =>
                  update('awsSecretAccessKey', event.target.value)
                }
              />
            </EuiFormRow>
          </EuiFlexItem>
          <EuiFlexItem>
            <EuiFormRow
              label="AWS session token"
              helpText="Optional; required for temporary credentials."
            >
              <EuiFieldPassword
                type="dual"
                value={input.awsSessionToken}
                autoComplete="new-password"
                onChange={(event) =>
                  update('awsSessionToken', event.target.value)
                }
              />
            </EuiFormRow>
          </EuiFlexItem>
        </EuiFlexGroup>
      )}
      <EuiSpacer size="m" />
      <EuiButton fill onClick={save} isLoading={saving} iconType="save">
        Save credentials locally
      </EuiButton>
    </EuiForm>
  );
}

function ConfigurationForm({
  initial,
  onSaved,
}: {
  initial: DeploymentConfig;
  onSaved: (config: DeploymentConfig) => void;
}) {
  const [config, setConfig] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();

  const setField = (field: keyof DeploymentConfig, value: string) => {
    setConfig((current) => ({ ...current, [field]: value }));
  };
  const setTag = (key: string, value: string) => {
    setConfig((current) => ({
      ...current,
      company_tags: { ...current.company_tags, [key]: value },
    }));
  };

  const save = async () => {
    setSaving(true);
    setError(undefined);
    try {
      const saved = await api.saveConfig(config);
      onSaved(saved.config);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <EuiForm component="form">
      {error && (
        <>
          <EuiCallOut color="danger" title={error} />
          <EuiSpacer size="m" />
        </>
      )}
      <EuiFlexGroup>
        <EuiFlexItem>
          <EuiFormRow label="Elastic project name">
            <EuiFieldText
              value={config.elastic_project_name}
              onChange={(event) =>
                setField('elastic_project_name', event.target.value)
              }
            />
          </EuiFormRow>
        </EuiFlexItem>
        <EuiFlexItem>
          <EuiFormRow label="Elastic region">
            <EuiFieldText
              value={config.elastic_region}
              onChange={(event) => setField('elastic_region', event.target.value)}
            />
          </EuiFormRow>
        </EuiFlexItem>
        <EuiFlexItem>
          <EuiFormRow label="AWS bootstrap region">
            <EuiFieldText
              value={config.aws_region}
              onChange={(event) => setField('aws_region', event.target.value)}
            />
          </EuiFormRow>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiFlexGroup>
        <EuiFlexItem>
          <EuiFormRow
            label="Collector instance type"
            helpText="The existing PR 12 architecture creates one EC2 collector."
          >
            <EuiFieldText
              value={config.elastic_agent_instance_type}
              onChange={(event) =>
                setField('elastic_agent_instance_type', event.target.value)
              }
            />
          </EuiFormRow>
        </EuiFlexItem>
        <EuiFlexItem>
          <EuiFormRow
            label="Existing CloudTrail bucket"
            helpText="Leave empty to use the Terraform default."
          >
            <EuiFieldText
              value={config.existing_cloudtrail_bucket_name}
              onChange={(event) =>
                setField('existing_cloudtrail_bucket_name', event.target.value)
              }
            />
          </EuiFormRow>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiHorizontalRule margin="m" />
      <EuiSwitch
        label="Elastic tags required"
        checked={config.elastic_tags_required}
        onChange={(event) =>
          setConfig((current) => ({
            ...current,
            elastic_tags_required: event.target.checked,
          }))
        }
      />
      {config.elastic_tags_required && (
        <>
          <EuiSpacer size="m" />
          <EuiTitle size="xxs">
            <h4>Organization-specific tags</h4>
          </EuiTitle>
          <EuiText size="xs" color="subdued">
            <p>
              These tags are sanitized for the Elastic project and propagated to
              taggable AWS resources created by this deployment.
            </p>
          </EuiText>
          <EuiSpacer size="s" />
          <EuiFlexGroup wrap>
            {config.required_tag_keys.map((key) => (
              <EuiFlexItem key={key} grow={false} css={{ width: 230 }}>
                <EuiFormRow label={key}>
                  <EuiFieldText
                    value={config.company_tags[key] ?? ''}
                    onChange={(event) => setTag(key, event.target.value)}
                  />
                </EuiFormRow>
              </EuiFlexItem>
            ))}
          </EuiFlexGroup>
        </>
      )}
      <EuiSpacer size="m" />
      <EuiButton fill onClick={save} isLoading={saving}>
        Save local configuration
      </EuiButton>
      <EuiText size="xs" color="subdued">
        <p>
          Written to <code>examples/aws/aws-poc-ui.auto.tfvars.json</code>.
          Credentials are read only from the local process environment.
        </p>
      </EuiText>
    </EuiForm>
  );
}

function RunPanel({
  run,
  nextAction,
}: {
  run?: RunRecord;
  nextAction?: string;
}) {
  if (!run) return null;
  const blocked = run.result?.passed === false;
  const latestActivity = [...run.logs]
    .reverse()
    .find((line) => line.trim() && !line.startsWith('$ '));
  const color =
    blocked
      ? 'danger'
      : run.status === 'succeeded'
      ? 'success'
      : run.status === 'failed'
        ? 'danger'
        : 'primary';
  return (
    <EuiPanel hasBorder>
      {run.status === 'running' && (
        <EuiProgress size="xs" color="primary" />
      )}
      <EuiFlexGroup alignItems="center" justifyContent="spaceBetween">
        <EuiFlexItem>
          <EuiTitle size="xs">
            <h3>{run.title}</h3>
          </EuiTitle>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiHealth color={color}>
            {run.status === 'running' && <EuiLoadingSpinner size="s" />}{' '}
            {blocked ? 'blocked' : run.status}
            {' · '}
            <ElapsedTime
              startedAt={run.startedAt}
              finishedAt={run.finishedAt}
            />
          </EuiHealth>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer size="s" />
      {run.status === 'running' && latestActivity && (
        <>
          <EuiPanel color="primary" paddingSize="s">
            <EuiText size="s">
              <p aria-live="polite">
                <strong>Current activity:</strong> {latestActivity}
              </p>
            </EuiText>
          </EuiPanel>
          <EuiSpacer size="s" />
        </>
      )}
      {run.step === 'discovery' && (
        <>
          <DiscoveryRegionProgress logs={run.logs} />
          <EuiSpacer size="s" />
        </>
      )}
      <EuiText size="s" color="subdued">
        <p>
          {run.status === 'running'
            ? 'Keep this page open. Live command output appears below and the next step unlocks automatically after this operation succeeds.'
            : run.status === 'failed' || blocked
              ? run.step === 'apply'
                ? 'Apply stopped after partial changes. Review the output, correct the issue, then create and review a fresh plan before applying again.'
                : 'This operation did not complete. Review the output below, correct the reported issue, and retry this step.'
              : nextAction
                ? `${nextAction} is now available.`
                : 'Operation completed successfully.'}
        </p>
      </EuiText>
      <EuiSpacer size="s" />
      <EuiCodeBlock
        language="shell"
        fontSize="s"
        paddingSize="s"
        overflowHeight={320}
        isCopyable
      >
        {run.logs.length ? run.logs.join('\n') : 'Waiting for output…'}
      </EuiCodeBlock>
    </EuiPanel>
  );
}

function PreflightResults({ checks }: { checks?: PreflightCheck[] }) {
  if (!checks?.length) return null;
  return (
    <>
      <EuiSpacer size="m" />
      <EuiPanel hasBorder paddingSize="s">
        {checks.map((check, index) => (
          <div key={check.id}>
            {check.status === 'passed' ? (
              <EuiHealth color="success">
                <strong>{check.label}:</strong> {check.detail}
              </EuiHealth>
            ) : (
              <EuiCallOut
                size="s"
                color={check.status === 'warning' ? 'warning' : 'danger'}
                title={`${check.label} needs attention`}
              >
                <p>{check.detail}</p>
              </EuiCallOut>
            )}
            {index < checks.length - 1 && <EuiSpacer size="s" />}
          </div>
        ))}
      </EuiPanel>
    </>
  );
}

function PlanResourceTable({ summary }: { summary?: PlanSummary | null }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  if (!summary) return null;
  if (summary.resources.length === 0) {
    return (
      <EuiCallOut
        size="s"
        color="success"
        title="No managed resource changes"
      >
        <p>Terraform found no resources to create, update, replace, or delete.</p>
      </EuiCallOut>
    );
  }
  const badgeColor = {
    create: 'success',
    update: 'primary',
    replace: 'warning',
    delete: 'danger',
    read: 'default',
  } as const;
  const columns: EuiBasicTableColumn<PlannedResource>[] = [
    {
      field: 'action',
      name: 'Action',
      width: '110px',
      render: (action: PlannedResource['action']) => (
        <EuiBadge color={badgeColor[action]}>{action.toUpperCase()}</EuiBadge>
      ),
    },
    {
      field: 'address',
      name: 'Terraform resource',
      render: (address: string) => <code>{address}</code>,
    },
    { field: 'type', name: 'Resource type' },
    { field: 'module', name: 'Module' },
  ];
  const firstItem = pageIndex * pageSize;
  const visibleResources = summary.resources.slice(
    firstItem,
    firstItem + pageSize,
  );
  const countItems = (
    ['create', 'update', 'replace', 'delete'] as const
  ).filter((action) => summary.counts[action] > 0);
  return (
    <>
      <EuiFlexGroup gutterSize="s" wrap>
        {countItems.map((action) => (
          <EuiFlexItem key={action} grow={false}>
            <EuiBadge color={badgeColor[action]}>
              {summary.counts[action]} {action}
            </EuiBadge>
          </EuiFlexItem>
        ))}
      </EuiFlexGroup>
      <EuiSpacer size="s" />
      <EuiBasicTable
        items={visibleResources}
        columns={columns}
        tableCaption="Managed resources changed by the saved Terraform plan"
        pagination={{
          pageIndex,
          pageSize,
          totalItemCount: summary.resources.length,
          pageSizeOptions: [10, 25, 50],
        }}
        onChange={({ page }: Criteria<PlannedResource>) => {
          if (!page) return;
          setPageIndex(page.index);
          setPageSize(page.size);
        }}
      />
    </>
  );
}

function PlanProgress({
  run,
  summary,
}: {
  run?: RunRecord;
  summary?: PlanSummary | null;
}) {
  if (!run) {
    if (!summary) return null;
    return (
      <EuiPanel hasBorder>
        <EuiTitle size="xs">
          <h3>Resources in the saved deployment plan</h3>
        </EuiTitle>
        <EuiText size="s" color="subdued">
          <p>
            Review every managed resource change before applying this plan.
          </p>
        </EuiText>
        <EuiSpacer size="m" />
        <PlanResourceTable summary={summary} />
      </EuiPanel>
    );
  }
  const output = run.logs.join('\n');
  const inspecting =
    /\bReading\.\.\.|\bRefreshing state\.\.\.|Read complete|existing-source/i.test(
      output,
    );
  const planBuilt = /(?:^|\n)(?:Plan:|No changes\.)/m.test(output);
  const activeStage = planBuilt ? 2 : inspecting ? 1 : 0;
  const stages = [
    {
      title: 'Prepare',
      description: 'Load configuration and providers',
    },
    {
      title: 'Inspect environment',
      description: 'Read existing AWS and Elastic state',
    },
    {
      title: 'Build reviewable plan',
      description: 'Calculate and save proposed changes',
    },
  ];
  const completedStages =
    run.status === 'succeeded'
      ? stages.length
      : run.status === 'running'
        ? activeStage
        : activeStage;

  return (
    <EuiPanel hasBorder>
      <EuiFlexGroup alignItems="center" justifyContent="spaceBetween">
        <EuiFlexItem>
          <EuiTitle size="xs">
            <h3>Deployment plan progress</h3>
          </EuiTitle>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiHealth
            color={
              run.status === 'succeeded'
                ? 'success'
                : run.status === 'failed'
                  ? 'danger'
                  : 'primary'
            }
          >
            {run.status === 'running' ? 'Working' : run.status}
          </EuiHealth>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer size="s" />
      <EuiProgress
        value={
          run.status === 'succeeded'
            ? stages.length
            : Math.min(activeStage + 0.5, stages.length)
        }
        max={stages.length}
        color={
          run.status === 'succeeded'
            ? 'success'
            : run.status === 'failed'
              ? 'danger'
              : 'primary'
        }
        size="m"
      />
      <EuiSpacer size="m" />
      <EuiFlexGroup gutterSize="s" responsive={false}>
        {stages.map((stage, index) => {
          const complete = index < completedStages;
          const active = run.status === 'running' && index === activeStage;
          const failed = run.status === 'failed' && index === activeStage;
          return (
            <EuiFlexItem key={stage.title}>
              <EuiPanel
                paddingSize="s"
                color={active ? 'primary' : 'plain'}
                hasBorder
              >
                <EuiHealth
                  color={
                    complete
                      ? 'success'
                      : failed
                        ? 'danger'
                        : active
                          ? 'primary'
                          : 'subdued'
                  }
                >
                  <strong>{stage.title}</strong>
                </EuiHealth>
                <EuiText size="xs" color="subdued">
                  <p>
                    {complete
                      ? 'Done'
                      : failed
                        ? 'Needs attention'
                        : active
                          ? 'Working…'
                          : 'Waiting'}
                    {' · '}
                    {stage.description}
                  </p>
                </EuiText>
              </EuiPanel>
            </EuiFlexItem>
          );
        })}
      </EuiFlexGroup>
      {run.status === 'failed' && (
        <>
          <EuiSpacer size="m" />
          <EuiCallOut
            size="s"
            color="danger"
            title="Terraform could not finish the plan"
          >
            <p>Open technical output below, correct the error, and retry.</p>
          </EuiCallOut>
        </>
      )}
      <EuiSpacer size="m" />
      <PlanResourceTable summary={summary} />
      {summary && <EuiSpacer size="m" />}
      <details>
        <summary style={{ cursor: 'pointer' }}>Show technical output</summary>
        <EuiSpacer size="s" />
        <EuiCodeBlock
          language="shell"
          fontSize="s"
          paddingSize="s"
          overflowHeight={240}
          isCopyable
        >
          {run.logs.length ? run.logs.join('\n') : 'Waiting for output…'}
        </EuiCodeBlock>
      </details>
    </EuiPanel>
  );
}

function BrownfieldResults({ status }: { status: BrownfieldStatus }) {
  if (!status.manifest && !status.analysis) {
    return (
      <EuiCallOut
        color="primary"
        title="No local brownfield results yet"
      >
        <p>
          Discovery reads AWS control-plane APIs only. Analysis works from the
          resulting local manifest and performs no cloud changes.
        </p>
      </EuiCallOut>
    );
  }
  const manifest = status.manifest?.summary;
  const analysis = status.analysis?.summary;
  const stats = [
    ['Resources', manifest?.resources ?? 0],
    ['Control-plane edges', manifest?.edges ?? 0],
    ['Service candidates', analysis?.service_candidates ?? manifest?.service_resources ?? 0],
    ['Dependencies', analysis?.dependencies ?? 0],
    ['Findings', analysis?.findings ?? 0],
    ['Proposals', analysis?.proposals ?? 0],
    [
      'Observed required coverage',
      analysis?.required_coverage?.percentage == null
        ? 'unknown'
        : `${analysis.required_coverage.percentage}%`,
    ],
  ] as const;
  return (
    <>
      <EuiFlexGroup wrap>
        {stats.map(([title, value]) => (
          <EuiFlexItem key={title} grow={false} css={{ minWidth: 150 }}>
            <EuiPanel hasBorder paddingSize="m">
              <EuiStat title={String(value)} description={title} titleSize="s" />
            </EuiPanel>
          </EuiFlexItem>
        ))}
      </EuiFlexGroup>
      <EuiSpacer size="m" />
      {manifest?.errors ? (
        <>
          <EuiCallOut
            color="warning"
            title={`Discovery completed with ${manifest.errors} partial scope error(s)`}
          >
            <p>Download the manifest to review denied or unavailable APIs.</p>
          </EuiCallOut>
          <EuiSpacer size="m" />
        </>
      ) : null}
      <EuiFlexGroup gutterSize="s" wrap>
        {status.manifest && (
          <EuiFlexItem grow={false}>
            <EuiButtonEmpty
              href="/api/brownfield/manifest"
              target="_blank"
              iconType="download"
            >
              Download manifest
            </EuiButtonEmpty>
          </EuiFlexItem>
        )}
        {status.analysis && (
          <EuiFlexItem grow={false}>
            <EuiButtonEmpty
              href="/api/brownfield/analysis"
              target="_blank"
              iconType="download"
            >
              Download analysis
            </EuiButtonEmpty>
          </EuiFlexItem>
        )}
      </EuiFlexGroup>
      {status.analysis?.limitations.length ? (
        <>
          <EuiSpacer size="m" />
          <EuiText size="xs" color="subdued">
            <p>{status.analysis.limitations[0]}</p>
          </EuiText>
        </>
      ) : null}
    </>
  );
}

function VisibilityExpansionOptions({
  status,
  onUpdated,
  onDeploy,
  onRollback,
  deployRun,
  rollbackRun,
  operationRunning,
}: {
  status: VisibilityExpansionStatus;
  onUpdated: (status: VisibilityExpansionStatus) => void;
  onDeploy: () => void;
  onRollback: () => void;
  deployRun?: RunRecord;
  rollbackRun?: RunRecord;
  operationRunning: boolean;
}) {
  const [saving, setSaving] = useState<string>();
  const [error, setError] = useState<string>();
  if (!status.options.length) return null;
  const approvedCount = status.selectedProposalIds.filter((id) => {
    const approval = status.approvals[id];
    return (
      approval?.ownerApproved &&
      approval.costReviewed &&
      approval.rollbackReviewed
    );
  }).length;
  const optionByProposalId = new Map(
    status.options.map((option) => [option.recommendedCanary.id, option]),
  );
  const readyToDeploy = status.selectedProposalIds.filter((id) => {
    const option = optionByProposalId.get(id);
    const approval = status.approvals[id];
    return (
      option?.adapter.available &&
      approval?.ownerApproved &&
      approval.costReviewed &&
      approval.rollbackReviewed &&
      !status.deployedProposalIds.includes(id)
    );
  });
  const toggle = async (proposalId: string) => {
    setSaving(proposalId);
    setError(undefined);
    const selected = status.selectedProposalIds.includes(proposalId)
      ? status.selectedProposalIds.filter((id) => id !== proposalId)
      : [...status.selectedProposalIds, proposalId];
    try {
      onUpdated(
        await api.saveVisibilityExpansions(selected, status.approvals),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(undefined);
    }
  };
  const updateApproval = async (
    proposalId: string,
    key: 'ownerApproved' | 'costReviewed' | 'rollbackReviewed',
    checked: boolean,
  ) => {
    setSaving(`${proposalId}:${key}`);
    setError(undefined);
    const current = status.approvals[proposalId] ?? {
      ownerApproved: false,
      costReviewed: false,
      rollbackReviewed: false,
    };
    try {
      onUpdated(
        await api.saveVisibilityExpansions(
          status.selectedProposalIds,
          {
            ...status.approvals,
            [proposalId]: { ...current, [key]: checked },
          },
        ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setSaving(undefined);
    }
  };
  return (
    <>
      <EuiHorizontalRule margin="m" />
      <EuiTitle size="xs">
        <h3>Expand visibility for this PoC</h3>
      </EuiTitle>
      <EuiText size="s" color="subdued">
        <p>
          Analysis found the following customer-workload canaries. Add only the
          highest-priority target in each category to the PoC scope, then review
          its prerequisites, cost dimensions, validation, and rollback before
          deployment.
        </p>
      </EuiText>
      {error && (
        <>
          <EuiCallOut color="danger" title={error} />
          <EuiSpacer size="m" />
        </>
      )}
      <EuiFlexGroup wrap>
        {status.options.map((option) => {
          const proposal = option.recommendedCanary;
          const selected = status.selectedProposalIds.includes(proposal.id);
          const approval = status.approvals[proposal.id] ?? {
            ownerApproved: false,
            costReviewed: false,
            rollbackReviewed: false,
          };
          const approvalComplete =
            approval.ownerApproved &&
            approval.costReviewed &&
            approval.rollbackReviewed;
          const deployed = status.deployedProposalIds.includes(proposal.id);
          return (
            <EuiFlexItem key={option.id} css={{ minWidth: 300 }}>
              <EuiPanel hasBorder color={selected ? 'primary' : 'plain'}>
                <EuiFlexGroup
                  alignItems="center"
                  justifyContent="spaceBetween"
                  gutterSize="s"
                >
                  <EuiFlexItem>
                    <EuiTitle size="xxs">
                      <h4>{option.title}</h4>
                    </EuiTitle>
                  </EuiFlexItem>
                  <EuiFlexItem grow={false}>
                    <EuiBadge color="hollow">
                      {option.affectedResources} candidates
                    </EuiBadge>
                  </EuiFlexItem>
                </EuiFlexGroup>
                <EuiSpacer size="s" />
                <EuiText size="s">
                  <p>{proposal.change_summary}</p>
                  <p>
                    <strong>Recommended canary:</strong>{' '}
                    {proposal.resource_name}
                  </p>
                </EuiText>
                <details>
                  <summary style={{ cursor: 'pointer' }}>
                    Review deployment safeguards
                  </summary>
                  <EuiText size="xs">
                    <p>
                      <strong>Prerequisites:</strong>{' '}
                      {proposal.prerequisites.join('; ')}
                    </p>
                    <p>
                      <strong>Cost:</strong>{' '}
                      {proposal.cost_dimensions.join('; ')}
                    </p>
                    <p>
                      <strong>Validation:</strong>{' '}
                      {proposal.validation.join('; ')}
                    </p>
                    <p>
                      <strong>Rollback:</strong> {proposal.rollback.join('; ')}
                    </p>
                  </EuiText>
                </details>
                <EuiSpacer size="m" />
                <EuiHealth
                  color={
                    deployed
                      ? 'success'
                      : option.adapter.available
                        ? 'primary'
                        : 'subdued'
                  }
                >
                  {deployed
                    ? 'Deployed'
                    : option.adapter.available
                      ? option.adapter.label
                      : option.adapter.label}
                </EuiHealth>
                <EuiSpacer size="s" />
                <EuiButton
                  size="s"
                  fill={!selected}
                  color={selected ? 'text' : 'primary'}
                  isLoading={saving === proposal.id}
                  isDisabled={deployed || saving !== undefined}
                  onClick={() => void toggle(proposal.id)}
                >
                  {deployed
                    ? 'Roll back before removing'
                    : selected
                      ? 'Remove from PoC scope'
                      : 'Add canary to PoC scope'}
                </EuiButton>
                {selected && (
                  <>
                    <EuiHorizontalRule margin="m" />
                    <EuiTitle size="xxs">
                      <h4>Deployment approval</h4>
                    </EuiTitle>
                    <EuiSpacer size="s" />
                    <EuiCheckbox
                      id={`${proposal.id}-owner`}
                      label="Workload owner approved this canary"
                      checked={approval.ownerApproved}
                      disabled={saving !== undefined}
                      onChange={(event) =>
                        void updateApproval(
                          proposal.id,
                          'ownerApproved',
                          event.target.checked,
                        )
                      }
                    />
                    <EuiSpacer size="s" />
                    <EuiCheckbox
                      id={`${proposal.id}-cost`}
                      label="Cost dimensions reviewed"
                      checked={approval.costReviewed}
                      disabled={saving !== undefined}
                      onChange={(event) =>
                        void updateApproval(
                          proposal.id,
                          'costReviewed',
                          event.target.checked,
                        )
                      }
                    />
                    <EuiSpacer size="s" />
                    <EuiCheckbox
                      id={`${proposal.id}-rollback`}
                      label="Rollback procedure reviewed"
                      checked={approval.rollbackReviewed}
                      disabled={saving !== undefined}
                      onChange={(event) =>
                        void updateApproval(
                          proposal.id,
                          'rollbackReviewed',
                          event.target.checked,
                        )
                      }
                    />
                    <EuiSpacer size="s" />
                    <EuiHealth
                      color={approvalComplete ? 'success' : 'warning'}
                    >
                      {approvalComplete
                        ? 'Approval controls complete'
                        : 'Approval required before deployment'}
                    </EuiHealth>
                  </>
                )}
              </EuiPanel>
            </EuiFlexItem>
          );
        })}
      </EuiFlexGroup>
      <EuiSpacer size="m" />
      <EuiCallOut
        color={status.selectedProposalIds.length ? 'warning' : 'primary'}
        title={
          status.selectedProposalIds.length
            ? `${approvedCount} of ${status.selectedProposalIds.length} selected canaries approved`
            : 'No workload changes selected'
        }
      >
        <p>
          Approval readiness and adapter readiness are separate controls.
          Workload instrumentation remains non-executing until all approvals
          are complete and a deployment adapter is available.
        </p>
      </EuiCallOut>
      <EuiSpacer size="m" />
      <EuiFlexGroup gutterSize="s" wrap>
        <EuiFlexItem grow={false}>
          <EuiButton
            fill
            iconType="launch"
            onClick={onDeploy}
            isLoading={deployRun?.status === 'running'}
            isDisabled={!readyToDeploy.length || operationRunning}
          >
            {readyToDeploy.length === 1
              ? 'Deploy 1 approved canary'
              : `Deploy ${readyToDeploy.length} approved canaries`}
          </EuiButton>
        </EuiFlexItem>
        {status.deployedProposalIds.length > 0 && (
          <EuiFlexItem grow={false}>
            <EuiButton
              color="warning"
              onClick={onRollback}
              isLoading={rollbackRun?.status === 'running'}
              isDisabled={operationRunning}
            >
              Roll back deployed canaries
            </EuiButton>
          </EuiFlexItem>
        )}
      </EuiFlexGroup>
      <EuiSpacer size="m" />
      <RunPanel run={deployRun} nextAction="Validate incoming visibility" />
      <RunPanel run={rollbackRun} />
    </>
  );
}

export default function App() {
  const [loadState, setLoadState] = useState<AsyncState>('loading');
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [credentials, setCredentials] = useState<CredentialsStatus>();
  const [brownfield, setBrownfield] = useState<BrownfieldStatus>();
  const [planSummary, setPlanSummary] = useState<PlanSummary | null>(null);
  const [visibilityExpansions, setVisibilityExpansions] =
    useState<VisibilityExpansionStatus>({
      options: [],
      selectedProposalIds: [],
      approvals: {},
      deployedProposalIds: [],
    });
  const [status, setStatus] = useState<DeploymentStatus>();
  const [config, setConfig] = useState<DeploymentConfig>();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeRun, setActiveRun] = useState<RunRecord>();
  const [pendingStep, setPendingStep] = useState<string>();
  const [error, setError] = useState<string>();
  const [confirmApply, setConfirmApply] = useState(false);

  const refresh = async () => {
    const [
      nextStatus,
      nextRuns,
      nextCredentials,
      nextBrownfield,
      nextPlanSummary,
      nextVisibilityExpansions,
    ] = await Promise.all([
      api.status(),
      api.runs(),
      api.credentials(),
      api.brownfield(),
      api.plan(),
      api.visibilityExpansions(),
    ]);
    setStatus(nextStatus);
    setRuns(nextRuns);
    setCredentials(nextCredentials);
    setBrownfield(nextBrownfield);
    setPlanSummary(nextPlanSummary);
    setVisibilityExpansions(nextVisibilityExpansions);
  };

  useEffect(() => {
    void Promise.all([
      api.bootstrap(),
      api.config(),
      api.runs(),
      api.brownfield(),
      api.plan(),
      api.visibilityExpansions(),
    ])
      .then(([
        loadedBootstrap,
        loadedConfig,
        loadedRuns,
        loadedBrownfield,
        loadedPlanSummary,
        loadedVisibilityExpansions,
      ]) => {
        setBootstrap(loadedBootstrap);
        setCredentials(loadedBootstrap.credentials);
        setStatus(loadedBootstrap.status);
        setConfig(loadedConfig.config);
        setRuns(loadedRuns);
        setBrownfield(loadedBrownfield);
        setPlanSummary(loadedPlanSummary);
        setVisibilityExpansions(loadedVisibilityExpansions);
        setActiveRun(loadedRuns.find((run) => run.status === 'running'));
        setLoadState('ready');
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : String(caught));
        setLoadState('error');
      });
  }, []);

  const latestPreflight = useMemo(
    () => runs.find((run) => run.step === 'preflight'),
    [runs],
  );
  const latestPreflightPassed =
    latestPreflight?.status === 'succeeded' &&
    latestPreflight.result?.passed === true;
  const initializationReady =
    latestPreflight?.status === 'succeeded' &&
    ['configuration', 'terraform'].every((id) =>
      latestPreflight.result?.checks?.some(
        (check) => check.id === id && check.status === 'passed',
      ),
    );

  const start = async (
    step: string,
    operation: () => Promise<RunRecord>,
  ): Promise<void> => {
    setError(undefined);
    setPendingStep(step);
    try {
      const run = await operation();
      if (run.step === 'plan') setPlanSummary(null);
      setActiveRun(run);
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      const unsubscribe = api.subscribe(run.id, (updated) => {
        setActiveRun(updated);
        setRuns((current) => [
          updated,
          ...current.filter((item) => item.id !== updated.id),
        ]);
        if (updated.status !== 'running') {
          unsubscribe();
          if (updated.status === 'succeeded') {
            setStatus((current) => {
              if (!current) return current;
              if (updated.step === 'init') {
                return { ...current, initialized: true };
              }
              if (updated.step === 'plan') {
                return { ...current, planned: true };
              }
              if (updated.step === 'apply') {
                return { ...current, planned: false, deployed: true };
              }
              return current;
            });
          }
          void refresh().catch((caught) => {
            setError(caught instanceof Error ? caught.message : String(caught));
          });
        }
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setPendingStep(undefined);
    }
  };

  if (loadState === 'loading') {
    return (
      <EuiPageTemplate>
        <EuiPageTemplate.Section alignment="center">
          <EuiLoadingSpinner size="xl" />
        </EuiPageTemplate.Section>
      </EuiPageTemplate>
    );
  }

  if (
    loadState === 'error' ||
    !bootstrap ||
    !credentials ||
    !brownfield ||
    !status ||
    !config
  ) {
    return (
      <EuiPageTemplate>
        <EuiPageTemplate.Section>
          <EuiCallOut color="danger" title="Unable to load the local guide">
            <p>{error}</p>
          </EuiCallOut>
        </EuiPageTemplate.Section>
      </EuiPageTemplate>
    );
  }

  const workflowIds = status.outputs.workflow_ids ?? [];
  const credentialsReady =
    credentials.elasticCloudApiKey.configured && credentials.aws.configured;
  const runFor = (step: string) => runs.find((run) => run.step === step);
  const operationRunning = (step: string) =>
    pendingStep === step ||
    (activeRun?.step === step && activeRun.status === 'running');
  const anyOperationRunning =
    pendingStep !== undefined || activeRun?.status === 'running';
  const steps = [
    {
      title: 'Store local credentials',
      status: credentialsReady ? ('complete' as const) : ('current' as const),
      children: (
        <CredentialsForm
          status={credentials}
          onSaved={(saved) => setCredentials(saved)}
        />
      ),
    },
    {
      title: 'Configure deployment',
      status: status.configured
        ? ('complete' as const)
        : credentialsReady
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <ConfigurationForm
          initial={config}
          onSaved={(saved) => {
            setConfig(saved);
            void refresh();
          }}
        />
      ),
    },
    {
      title: 'Check prerequisites',
      status:
        latestPreflightPassed
          ? ('complete' as const)
          : status.configured && credentialsReady
            ? ('current' as const)
            : ('disabled' as const),
      children: (
        <>
          <EuiText>
            <p>
              Checks Terraform, Python, the AWS caller identity and the local
              Elastic Cloud API key. Secret values stay in the server process.
            </p>
          </EuiText>
          <EuiButton
            onClick={() =>
              void start('preflight', () => api.startStep('preflight'))
            }
            isLoading={operationRunning('preflight')}
            isDisabled={
              !status.configured ||
              !credentialsReady ||
              anyOperationRunning
            }
          >
            {operationRunning('preflight')
              ? 'Checking prerequisites…'
              : 'Run preflight'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('preflight')}
            nextAction="Initialize Terraform"
          />
          <PreflightResults checks={latestPreflight?.result?.checks} />
        </>
      ),
    },
    {
      title: 'Initialize Terraform',
      status: status.initialized
        ? ('complete' as const)
        : initializationReady
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
          {!initializationReady && (
            <>
              <EuiCallOut
                color="warning"
                title="Check Terraform prerequisites first"
              >
                <p>
                  Initialization remains disabled until the saved configuration
                  and Terraform executable pass the prerequisite check above.
                  Cloud credentials are checked separately for planning.
                </p>
              </EuiCallOut>
              <EuiSpacer size="m" />
            </>
          )}
          <EuiText>
            <p>
              Downloads and prepares the required Terraform providers and
              modules. No AWS or Elastic resources are created in this step.
            </p>
          </EuiText>
          <EuiButton
            onClick={() => void start('init', () => api.startStep('init'))}
            isLoading={operationRunning('init')}
            isDisabled={
              !status.configured ||
              !credentialsReady ||
              !initializationReady ||
              anyOperationRunning
            }
          >
            {operationRunning('init')
              ? 'Initializing Terraform…'
              : status.initialized
                ? 'Initialize again'
                : 'Initialize Terraform'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('init')}
            nextAction="Review deployment plan"
          />
        </>
      ),
    },
    {
      title: 'Review deployment plan',
      status: status.planned || status.deployed
        ? ('complete' as const)
        : status.initialized && latestPreflightPassed
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
          {status.initialized && !latestPreflightPassed && (
            <>
              <EuiCallOut
                color="warning"
                title="Resolve cloud prerequisite checks before planning"
              >
                <p>
                  Terraform is initialized. Run preflight again after correcting
                  the failed AWS or Elastic credential check to unlock planning.
                </p>
              </EuiCallOut>
              <EuiSpacer size="m" />
            </>
          )}
          {!status.initialized && (
            <>
              <EuiCallOut
                color="primary"
                title="Complete Terraform initialization first"
              >
                <p>
                  This step unlocks automatically after Initialize Terraform
                  succeeds. If it stays disabled, review the inline output in
                  the previous step.
                </p>
              </EuiCallOut>
              <EuiSpacer size="m" />
            </>
          )}
          <EuiText>
            <p>
              Terraform performs existing-source discovery while planning. Review
              every AWS and Elastic change in the execution log before applying.
            </p>
          </EuiText>
          <EuiButton
            onClick={() => void start('plan', () => api.startStep('plan'))}
            isLoading={operationRunning('plan')}
            isDisabled={
              !status.initialized ||
              !latestPreflightPassed ||
              anyOperationRunning
            }
          >
            {operationRunning('plan') ? 'Creating plan…' : 'Create plan'}
          </EuiButton>
          <EuiSpacer size="m" />
          <PlanProgress run={runFor('plan')} summary={planSummary} />
        </>
      ),
    },
    {
      title: 'Deploy collectors and Elastic content',
      status: status.deployed
        ? ('complete' as const)
        : status.planned
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
          <EuiCallOut
            color="warning"
            iconType="warning"
            title="This creates AWS and Elastic resources"
          >
            <p>
              It does not create a sample application, but the current PR 12
              architecture creates collection infrastructure and enables regional
              security services. Confirm the reviewed plan before continuing.
            </p>
          </EuiCallOut>
          <EuiSpacer size="m" />
          <EuiButton
            fill
            color="warning"
            onClick={() => setConfirmApply(true)}
            isLoading={operationRunning('apply')}
            isDisabled={!status.planned || anyOperationRunning}
          >
            {operationRunning('apply')
              ? 'Applying reviewed plan…'
              : 'Apply reviewed plan'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('apply')}
            nextAction="Discover customer environment"
          />
        </>
      ),
    },
    {
      title: 'Discover the existing AWS environment',
      status: brownfield.manifest
        ? ('complete' as const)
        : credentialsReady
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
          <EuiText>
            <p>
              Runs bounded, read-only AWS CLI discovery across enabled Regions.
              It inventories existing compute, serverless, load-balancing,
              database, messaging, alarm, log, and X-Ray resources.
            </p>
          </EuiText>
          <EuiButton
            onClick={() =>
              void start('discovery', () => api.startStep('discovery'))
            }
            isLoading={operationRunning('discovery')}
            isDisabled={!credentialsReady || anyOperationRunning}
          >
            {operationRunning('discovery')
              ? 'Discovering customer environment…'
              : 'Discover customer environment'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('discovery')}
            nextAction="Analyze discovered services"
          />
        </>
      ),
    },
    {
      title: 'Analyze services, dependencies and gaps',
      status: brownfield.analysis
        ? ('complete' as const)
        : brownfield.manifest
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
          <EuiText>
            <p>
              Deterministically derives service candidates, evidence-scored
              dependencies, telemetry coverage, health and ownership findings,
              and non-executing instrumentation proposals.
            </p>
          </EuiText>
          <EuiButton
            onClick={() =>
              void start('analysis', () => api.startStep('analysis'))
            }
            isLoading={operationRunning('analysis')}
            isDisabled={!brownfield.manifest || anyOperationRunning}
          >
            {operationRunning('analysis')
              ? 'Analyzing local manifest…'
              : 'Analyze local manifest'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('analysis')}
            nextAction="Review findings and instrumentation proposals"
          />
          <EuiSpacer size="m" />
          <BrownfieldResults status={brownfield} />
          {brownfield.analysis && (
            <VisibilityExpansionOptions
              status={visibilityExpansions}
              onUpdated={setVisibilityExpansions}
              onDeploy={() =>
                void start('visibility:deploy', () =>
                  api.deployVisibilityExpansions(),
                )
              }
              onRollback={() =>
                void start('visibility:rollback', () =>
                  api.rollbackVisibilityExpansions(),
                )
              }
              deployRun={runFor('visibility:deploy')}
              rollbackRun={runFor('visibility:rollback')}
              operationRunning={anyOperationRunning}
            />
          )}
        </>
      ),
    },
    {
      title: 'Refresh Elastic insights',
      status: status.deployed ? ('current' as const) : ('disabled' as const),
      children: (
        <>
          <EuiText>
            <p>
              Refresh recommendations and PoC evidence from telemetry already
              collected by Elastic.
            </p>
          </EuiText>
          <EuiButton
            iconType="refresh"
            onClick={() =>
              void start('workflows:all', () => api.runAllWorkflows())
            }
            isLoading={operationRunning('workflows:all')}
            isDisabled={!workflowIds.length || anyOperationRunning}
          >
            {operationRunning('workflows:all')
              ? 'Refreshing Elastic insights…'
              : 'Refresh Elastic insights'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('workflows:all')}
            nextAction="Investigate results"
          />
          {!workflowIds.length && (
            <EuiCallOut
              color="primary"
              title="Insight automation becomes available after deployment"
            />
          )}
          {workflowIds.length > 0 && (
            <details>
              <summary style={{ cursor: 'pointer' }}>
                Technical workflow details
              </summary>
              <EuiText size="xs" color="subdued">
                <p>{workflowIds.join(', ')}</p>
              </EuiText>
            </details>
          )}
        </>
      ),
    },
    {
      title: 'Investigate results',
      status: status.deployed ? ('current' as const) : ('disabled' as const),
      children: (
        <EuiFlexGroup wrap>
          {status.outputs.cockpit_dashboard_url && (
            <EuiFlexItem grow={false}>
              <EuiButton
                href={status.outputs.cockpit_dashboard_url}
                target="_blank"
                iconSide="right"
                iconType="popout"
              >
                Open AWS cockpit
              </EuiButton>
            </EuiFlexItem>
          )}
          {status.outputs.kibana_url && (
            <EuiFlexItem grow={false}>
              <EuiButtonEmpty
                href={status.outputs.kibana_url}
                target="_blank"
                iconSide="right"
                iconType="popout"
              >
                Open Elastic
              </EuiButtonEmpty>
            </EuiFlexItem>
          )}
        </EuiFlexGroup>
      ),
    },
  ];

  return (
    <>
      <EuiHeader>
        <EuiHeaderSectionItem>
          <EuiFlexGroup alignItems="center" gutterSize="s" responsive={false}>
            <EuiFlexItem grow={false}>
              <EuiHeaderLogo iconTitle="Elastic" logoType="horizontal" />
            </EuiFlexItem>
            <EuiFlexItem grow={false}>
              <strong>Elastic PoC Deployment Creator</strong>
            </EuiFlexItem>
          </EuiFlexGroup>
        </EuiHeaderSectionItem>
        <EuiHeaderSectionItem>
          <EuiBadge color="hollow">localhost only</EuiBadge>
        </EuiHeaderSectionItem>
      </EuiHeader>
      <EuiPageTemplate paddingSize="l">
        <EuiPageTemplate.Header
          pageTitle="Deploy AWS Observability"
          description="Guided local deployment from this customer workstation"
          rightSideItems={[
            <EuiButtonEmpty
              key="refresh"
              iconType="refresh"
              onClick={() => void refresh()}
            >
              Refresh status
            </EuiButtonEmpty>,
          ]}
        />
        <EuiPageTemplate.Section>
          {error && (
            <>
              <EuiCallOut color="danger" title={error} />
              <EuiSpacer size="m" />
            </>
          )}
          <EuiPanel color="subdued" hasBorder>
            <EuiFlexGroup wrap>
              <EuiFlexItem>
                <EuiText size="s">
                  <strong>Repository</strong>
                  <br />
                  <code>{bootstrap.repoRoot}</code>
                </EuiText>
              </EuiFlexItem>
              <EuiFlexItem>
                <EuiText size="s">
                  <strong>Terraform directory</strong>
                  <br />
                  <code>{bootstrap.terraformDirectory}</code>
                </EuiText>
              </EuiFlexItem>
              {status.outputs.aws_account_id && (
                <EuiFlexItem grow={false}>
                  <EuiText size="s">
                    <strong>AWS account</strong>
                    <br />
                    {status.outputs.aws_account_id}
                  </EuiText>
                </EuiFlexItem>
              )}
            </EuiFlexGroup>
          </EuiPanel>
          <EuiSpacer size="l" />
          <EuiSteps steps={steps} titleSize="s" />
          {runs.length > 0 && (
            <>
              <EuiSpacer size="l" />
              <EuiText size="s" color="subdued">
                <p>
                  Latest operation: {runs[0].title} — {runs[0].status}. Execution
                  logs are kept only in this local process.
                </p>
              </EuiText>
            </>
          )}
          <EuiSpacer size="xl" />
          <EuiText size="xs" color="subdued">
            <p>
              This interface runs on loopback only. Review the{' '}
              <EuiLink href="https://www.elastic.co/guide/en/cloud/current/ec-api-authentication.html" target="_blank">
                Elastic API key guidance
              </EuiLink>{' '}
              and your organization&apos;s AWS change process before deployment.
            </p>
          </EuiText>
        </EuiPageTemplate.Section>
      </EuiPageTemplate>
      {confirmApply && (
        <EuiConfirmModal
          title="Apply the reviewed Terraform plan?"
          onCancel={() => setConfirmApply(false)}
          onConfirm={() => {
            setConfirmApply(false);
            void start('apply', () => api.startStep('apply'));
          }}
          cancelButtonText="Cancel"
          confirmButtonText="Apply plan"
          buttonColor="danger"
          defaultFocusedButton="cancel"
        >
          <p>
            This runs the saved plan from the local workstation using its current
            AWS and Elastic credentials.
          </p>
        </EuiConfirmModal>
      )}
    </>
  );
}
