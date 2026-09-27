import { useEffect, useMemo, useState } from 'react';
import {
  EuiBadge,
  EuiButton,
  EuiButtonEmpty,
  EuiCallOut,
  EuiCodeBlock,
  EuiConfirmModal,
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
  EuiSpacer,
  EuiSteps,
  EuiText,
  EuiTitle,
} from '@elastic/eui';
import {
  api,
  type Bootstrap,
  type DeploymentConfig,
  type DeploymentStatus,
  type RunRecord,
} from './api';

type AsyncState = 'idle' | 'loading' | 'ready' | 'error';

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
      <EuiTitle size="xxs">
        <h4>Required company tags</h4>
      </EuiTitle>
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

function RunPanel({ run }: { run?: RunRecord }) {
  if (!run) return null;
  const color =
    run.status === 'succeeded'
      ? 'success'
      : run.status === 'failed'
        ? 'danger'
        : 'primary';
  return (
    <EuiPanel hasBorder>
      <EuiFlexGroup alignItems="center" justifyContent="spaceBetween">
        <EuiFlexItem>
          <EuiTitle size="xs">
            <h3>{run.title}</h3>
          </EuiTitle>
        </EuiFlexItem>
        <EuiFlexItem grow={false}>
          <EuiHealth color={color}>
            {run.status === 'running' && <EuiLoadingSpinner size="s" />} {run.status}
          </EuiHealth>
        </EuiFlexItem>
      </EuiFlexGroup>
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

export default function App() {
  const [loadState, setLoadState] = useState<AsyncState>('loading');
  const [bootstrap, setBootstrap] = useState<Bootstrap>();
  const [status, setStatus] = useState<DeploymentStatus>();
  const [config, setConfig] = useState<DeploymentConfig>();
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [activeRun, setActiveRun] = useState<RunRecord>();
  const [error, setError] = useState<string>();
  const [confirmApply, setConfirmApply] = useState(false);

  const refresh = async () => {
    const [nextStatus, nextRuns] = await Promise.all([api.status(), api.runs()]);
    setStatus(nextStatus);
    setRuns(nextRuns);
  };

  useEffect(() => {
    void Promise.all([api.bootstrap(), api.config(), api.runs()])
      .then(([loadedBootstrap, loadedConfig, loadedRuns]) => {
        setBootstrap(loadedBootstrap);
        setStatus(loadedBootstrap.status);
        setConfig(loadedConfig.config);
        setRuns(loadedRuns);
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

  const start = async (
    operation: () => Promise<RunRecord>,
  ): Promise<void> => {
    setError(undefined);
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

  if (loadState === 'error' || !bootstrap || !status || !config) {
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
  const steps = [
    {
      title: 'Configure deployment',
      status: status.configured ? ('complete' as const) : ('current' as const),
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
        latestPreflight?.status === 'succeeded'
          ? ('complete' as const)
          : status.configured
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
            onClick={() => void start(() => api.startStep('preflight'))}
            isDisabled={!status.configured || activeRun?.status === 'running'}
          >
            Run preflight
          </EuiButton>
        </>
      ),
    },
    {
      title: 'Initialize Terraform',
      status: status.initialized
        ? ('complete' as const)
        : status.configured
          ? ('current' as const)
          : ('disabled' as const),
      children: (
        <EuiButton
          onClick={() => void start(() => api.startStep('init'))}
          isDisabled={!status.configured || activeRun?.status === 'running'}
        >
          Initialize
        </EuiButton>
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
          <EuiText>
            <p>
              Terraform performs existing-source discovery while planning. Review
              every AWS and Elastic change in the execution log before applying.
            </p>
          </EuiText>
          <EuiButton
            onClick={() => void start(() => api.startStep('plan'))}
            isDisabled={!status.initialized || activeRun?.status === 'running'}
          >
            Create plan
          </EuiButton>
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
            isDisabled={!status.planned || activeRun?.status === 'running'}
          >
            Apply reviewed plan
          </EuiButton>
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
                    void start(() => api.runWorkflow(workflowId))
                  }
                  isDisabled={activeRun?.status === 'running'}
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
              <strong>AWS PoC Guide</strong>
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
          <EuiSpacer size="l" />
          <RunPanel run={activeRun} />
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
            void start(() => api.startStep('apply'));
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
