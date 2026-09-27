import { useEffect, useMemo, useState } from 'react';
import {
  EuiBadge,
  EuiButton,
  EuiButtonEmpty,
  EuiCallOut,
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
} from '@elastic/eui';
import {
  api,
  type Bootstrap,
  type BrownfieldStatus,
  type CredentialsInput,
  type CredentialsStatus,
  type DeploymentConfig,
  type DeploymentStatus,
  type PreflightCheck,
  type RunRecord,
} from './api';

type AsyncState = 'idle' | 'loading' | 'ready' | 'error';

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
          </EuiHealth>
        </EuiFlexItem>
      </EuiFlexGroup>
      <EuiSpacer size="s" />
      <EuiText size="s" color="subdued">
        <p>
          {run.status === 'running'
            ? 'Keep this page open. Live command output appears below and the next step unlocks automatically after this operation succeeds.'
            : run.status === 'failed' || blocked
              ? 'This operation did not complete. Review the output below, correct the reported issue, and retry this step.'
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
        {checks.map((check) => (
          <EuiHealth
            key={check.id}
            color={
              check.status === 'passed'
                ? 'success'
                : check.status === 'warning'
                  ? 'warning'
                  : 'danger'
            }
          >
            <strong>{check.label}:</strong> {check.detail}
          </EuiHealth>
        ))}
      </EuiPanel>
    </>
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

export default function App() {
  const [loadState, setLoadState] = useState<AsyncState>('loading');
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [credentials, setCredentials] = useState<CredentialsStatus>();
  const [brownfield, setBrownfield] = useState<BrownfieldStatus>();
  const [status, setStatus] = useState<DeploymentStatus>();
  const [config, setConfig] = useState<DeploymentConfig>();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeRun, setActiveRun] = useState<RunRecord>();
  const [pendingStep, setPendingStep] = useState<string>();
  const [error, setError] = useState<string>();
  const [confirmApply, setConfirmApply] = useState(false);

  const refresh = async () => {
    const [nextStatus, nextRuns, nextCredentials, nextBrownfield] = await Promise.all([
      api.status(),
      api.runs(),
      api.credentials(),
      api.brownfield(),
    ]);
    setStatus(nextStatus);
    setRuns(nextRuns);
    setCredentials(nextCredentials);
    setBrownfield(nextBrownfield);
  };

  useEffect(() => {
    void Promise.all([api.bootstrap(), api.config(), api.runs(), api.brownfield()])
      .then(([loadedBootstrap, loadedConfig, loadedRuns, loadedBrownfield]) => {
        setBootstrap(loadedBootstrap);
        setCredentials(loadedBootstrap.credentials);
        setStatus(loadedBootstrap.status);
        setConfig(loadedConfig.config);
        setRuns(loadedRuns);
        setBrownfield(loadedBrownfield);
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
          void refresh();
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
      status: status.planned
        ? ('complete' as const)
        : status.initialized
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <>
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
            isDisabled={!status.initialized || anyOperationRunning}
          >
            {operationRunning('plan') ? 'Creating plan…' : 'Create plan'}
          </EuiButton>
          <EuiSpacer size="m" />
          <RunPanel
            run={runFor('plan')}
            nextAction="Deploy collectors and Elastic content"
          />
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
              Run the deployed deterministic Workflows. These use customer
              telemetry already collected by Elastic.
            </p>
          </EuiText>
          <EuiFlexGroup wrap gutterSize="s">
            {workflowIds.map((workflowId) => (
              <EuiFlexItem key={workflowId} grow={false}>
                <EuiButtonEmpty
                  iconType="play"
                  onClick={() =>
                    void start(`workflow:${workflowId}`, () =>
                      api.runWorkflow(workflowId),
                    )
                  }
                  isLoading={operationRunning(`workflow:${workflowId}`)}
                  isDisabled={anyOperationRunning}
                >
                  {workflowId}
                </EuiButtonEmpty>
              </EuiFlexItem>
            ))}
            {workflowIds.length === 0 && (
              <EuiFlexItem>
                <EuiCallOut
                  color="primary"
                  title="No deployed workflows reported yet"
                />
              </EuiFlexItem>
            )}
          </EuiFlexGroup>
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
