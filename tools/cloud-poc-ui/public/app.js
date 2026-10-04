const steps = [
  {
    operation: 'preflight',
    label: 'Preflight',
    description: 'Validate credentials, required tools, and access to the named project.',
  },
  {
    operation: 'terraform-init',
    label: 'Initialize Terraform',
    description: 'Download and initialize the pinned providers and local modules.',
  },
  {
    operation: 'terraform-plan',
    label: 'Review saved plan',
    description: 'Create the exact plan and review its resource actions before applying.',
  },
  {
    operation: 'terraform-apply',
    label: 'Apply saved plan',
    description: 'Apply only the reviewed plan after typing the explicit confirmation.',
  },
  {
    operation: 'discovery',
    label: 'Discover GCP',
    description: 'Run bounded, read-only Cloud Asset Inventory discovery.',
  },
  {
    operation: 'analysis',
    label: 'Analyze coverage',
    description: 'Build coverage gaps, findings, and named visibility candidates.',
  },
  {
    operation: 'workflows',
    label: 'Run workflows',
    description: 'Run the allow-listed deterministic GCP insight workflows.',
  },
  {
    operation: 'final-links',
    label: 'Open final links',
    description: 'Open the Elastic cockpit and the selected GCP project.',
  },
];

let csrfToken = '';
let activeEvents;
let credentialState = {
  elasticConfigured: false,
  cloudConfigured: false,
};
let operationHistory = [];
let operationRunning = false;
const stepContainer = document.querySelector('#steps');
const guidedSummary = document.querySelector('#guided-summary');
const state = document.querySelector('#state');
const progress = document.querySelector('#progress');
const message = document.querySelector('#message');
const logs = document.querySelector('#logs');
const result = document.querySelector('#result');
const projectInput = document.querySelector('#projectId');
const credentialsForm = document.querySelector('#credentials');
const credentialsButton = document.querySelector('#save-credentials');
const credentialsStatus = document.querySelector('#credentials-status');
const applicationCredentialsFile = document.querySelector(
  '#applicationCredentialsFile',
);
const visibilityCandidates = document.querySelector('#visibility-candidates');
const visibilityMessage = document.querySelector('#visibility-message');
projectInput.value = localStorage.getItem('gcpProjectId') ?? '';
let lastAnalysisLoaded;

function setButtonsDisabled(disabled) {
  operationRunning = disabled;
  renderGuidedPath();
}

function latestOperation(operation, projectId) {
  return operationHistory
    .filter(
      (record) =>
        record.operation === operation &&
        record.projectId === projectId,
    )
    .sort((left, right) => right.startedAt.localeCompare(left.startedAt))[0];
}

function rememberOperation(operation) {
  operationHistory = [
    operation,
    ...operationHistory.filter((record) => record.id !== operation.id),
  ];
}

async function startGuidedOperation(operation) {
  const projectId = projectInput.value.trim();
  if (!projectId) {
    message.textContent = 'Enter the named GCP project ID first.';
    projectInput.focus();
    return;
  }
  localStorage.setItem('gcpProjectId', projectId);
  let confirmation;
  if (operation === 'terraform-apply') {
    confirmation = window.prompt('Type APPLY to apply the reviewed saved plan.');
    if (confirmation !== 'APPLY') return;
  }
  setButtonsDisabled(true);
  try {
    watchOperation(
      await api(`/api/providers/gcp/operations/${operation}`, {
        method: 'POST',
        body: JSON.stringify({ projectId, confirmation }),
      }),
    );
  } catch (error) {
    state.textContent = 'failed';
    state.classList.add('failed');
    message.textContent = error.message;
    setButtonsDisabled(false);
  }
}

function renderGuidedPath() {
  const projectId = projectInput.value.trim();
  const credentialsReady =
    credentialState.cloudConfigured && credentialState.elasticConfigured;
  const records = steps.map(({ operation }) =>
    projectId ? latestOperation(operation, projectId) : undefined,
  );
  const nextIndex = records.findIndex(
    (record) => record?.state !== 'succeeded',
  );
  const completed = records.filter(
    (record) => record?.state === 'succeeded',
  ).length;

  if (!credentialsReady) {
    guidedSummary.textContent =
      'Next: save both Elastic and Google Cloud credentials in step 1.';
  } else if (!projectId) {
    guidedSummary.textContent =
      'Credentials are saved. Next: enter the GCP project ID in step 2.';
  } else if (nextIndex === -1) {
    guidedSummary.textContent =
      `All ${steps.length} guided steps are complete for ${projectId}. ` +
      'You can reopen the final links or rerun any completed step.';
  } else {
    const next = steps[nextIndex];
    const failed = records[nextIndex]?.state === 'failed';
    guidedSummary.textContent =
      `${completed} of ${steps.length} steps complete for ${projectId}. ` +
      `${failed ? 'Needs attention' : 'Next'}: ${next.label}. ${next.description}`;
  }

  stepContainer.replaceChildren();
  steps.forEach((step, index) => {
    const record = records[index];
    const complete = record?.state === 'succeeded';
    const failed = record?.state === 'failed';
    const running = ['queued', 'running', 'validating'].includes(record?.state);
    const next = index === nextIndex;
    const locked =
      !credentialsReady ||
      !projectId ||
      (nextIndex !== -1 && index > nextIndex && !complete);
    const card = document.createElement('article');
    card.className = [
      'guided-step',
      complete ? 'complete' : '',
      failed ? 'failed' : '',
      next && !failed ? 'next' : '',
    ]
      .filter(Boolean)
      .join(' ');

    const number = document.createElement('span');
    number.className = 'step-number';
    number.textContent = String(index + 1);
    const copy = document.createElement('div');
    copy.className = 'step-copy';
    const heading = document.createElement('h3');
    heading.textContent = step.label;
    const description = document.createElement('p');
    description.textContent = step.description;
    copy.append(heading, description);
    if (record) {
      const history = document.createElement('p');
      history.className = 'step-history';
      const when = new Date(record.finishedAt ?? record.updatedAt).toLocaleString();
      history.textContent = complete
        ? `Completed ${when}.`
        : failed
          ? `Last attempt failed ${when}. Review the operation log below, then retry.`
          : `Started ${new Date(record.startedAt).toLocaleString()}.`;
      copy.append(history);
    }
    const status = document.createElement('span');
    status.className = 'step-status';
    status.textContent = complete
      ? 'Complete'
      : failed
        ? 'Needs attention'
        : running
          ? 'In progress'
          : next && credentialsReady && projectId
            ? 'Next'
            : 'Locked';
    const button = actionButton(
      complete ? 'Run again' : failed ? 'Retry step' : `Start ${step.label}`,
      () => void startGuidedOperation(step.operation),
      operationRunning || running || locked,
    );
    card.append(number, copy, status, button);
    appendFriendlyResult(card, step, record);
    stepContainer.append(card);
  });
}

function renderResult(value) {
  result.replaceChildren();
  if (!value) return;
  if (Array.isArray(value.resources)) {
    const table = document.createElement('table');
    const head = table.createTHead().insertRow();
    for (const heading of ['Action', 'Resource', 'Module']) {
      const cell = document.createElement('th');
      cell.textContent = heading;
      head.append(cell);
    }
    const body = table.createTBody();
    for (const resource of value.resources) {
      const row = body.insertRow();
      for (const text of [resource.action, resource.address, resource.module]) {
        const cell = row.insertCell();
        cell.textContent = text;
      }
    }
    result.append(table);
    return;
  }
  if (value.cloudConsole || value.cockpit) {
    for (const [label, href] of [
      ['Open the Elastic cockpit', value.cockpit],
      ['Open the GCP project', value.cloudConsole],
    ]) {
      if (!href) continue;
      const link = document.createElement('a');
      link.href = href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = label;
      result.append(link, document.createElement('br'));
    }
    return;
  }
  const summary = document.createElement('pre');
  summary.textContent = JSON.stringify(value, null, 2);
  result.append(summary);
}

function renderOperation(operation) {
  rememberOperation(operation);
  state.textContent = operation.state;
  state.classList.toggle('failed', operation.state === 'failed');
  progress.value = operation.percent ?? (operation.state === 'succeeded' ? 100 : 5);
  message.textContent = `${operation.stage}: ${operation.message}`;
  logs.textContent = operation.logs?.join('\n') || 'No command output for this operation.';
  renderResult(operation.result);
  const terminal = ['succeeded', 'failed', 'skipped', 'rolled-back'].includes(
    operation.state,
  );
  setButtonsDisabled(!terminal);
  if (terminal && activeEvents) {
    activeEvents.close();
    activeEvents = undefined;
  }
  if (
    operation.operation === 'analysis' &&
    operation.state === 'succeeded' &&
    lastAnalysisLoaded !== operation.id
  ) {
    lastAnalysisLoaded = operation.id;
    void loadVisibility();
  }
}

function watchOperation(operation) {
  renderOperation(operation);
  activeEvents?.close();
  activeEvents = new EventSource(`/api/operations/${operation.id}/events`);
  activeEvents.onmessage = (event) => renderOperation(JSON.parse(event.data));
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.method && options.method !== 'GET'
        ? { 'x-cloud-poc-csrf': csrfToken }
        : {}),
      ...options.headers,
    },
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.message ?? `Request failed (${response.status})`);
  return body;
}

function detail(list, label, value) {
  const term = document.createElement('dt');
  term.textContent = label;
  const description = document.createElement('dd');
  description.textContent = value;
  list.append(term, description);
}

function actionButton(label, handler, disabled = false) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener('click', handler);
  return button;
}

function appendText(container, label, value) {
  const row = document.createElement('p');
  const strong = document.createElement('strong');
  strong.textContent = `${label}: `;
  row.append(strong, document.createTextNode(String(value)));
  container.append(row);
}

function friendlyFailure(record) {
  const raw = record.logs?.join('\n') ?? '';
  if (raw.includes('No value for required variable')) {
    return (
      'Terraform was missing required deployment inputs. The selected project ' +
      'and PoC labels are now supplied automatically; retry this step.'
    );
  }
  if (raw.includes('not installed or is not on PATH')) {
    return 'A required local tool is unavailable. Follow the installation guidance in Advanced output, restart the UI, and retry.';
  }
  const errorLine = raw
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.startsWith('Error:') || line.startsWith('ERROR:'));
  return errorLine
    ? `${errorLine} Open Advanced output for the complete diagnostic.`
    : 'This step failed. Open Advanced output for the diagnostic, correct the issue, and retry.';
}

function appendFriendlyResult(container, step, record) {
  if (!record) return;
  const output = document.createElement('div');
  output.className = 'step-output';
  const heading = document.createElement('h4');
  heading.textContent =
    record.state === 'failed'
      ? 'What happened'
      : record.state === 'succeeded'
        ? 'Result'
        : 'Current activity';
  output.append(heading);

  if (record.state === 'failed') {
    const explanation = document.createElement('p');
    explanation.textContent = friendlyFailure(record);
    output.append(explanation);
  } else if (record.state !== 'succeeded') {
    appendText(output, 'Status', `${record.stage}: ${record.message}`);
    if (record.percent !== undefined) {
      appendText(output, 'Progress', `${record.percent}%`);
    }
  } else {
    const value = record.result ?? {};
    switch (step.operation) {
      case 'preflight':
        appendText(
          output,
          'Validated project',
          value.identity?.projectId ?? record.projectId,
        );
        appendText(
          output,
          'Tools',
          `Terraform ${value.tools?.terraform ?? 'available'}, gcloud ${value.tools?.gcloud ?? 'available'}`,
        );
        break;
      case 'terraform-init':
        appendText(output, 'Terraform', 'Providers and modules initialized successfully');
        break;
      case 'terraform-plan': {
        const counts = value.counts ?? {};
        appendText(
          output,
          'Planned actions',
          `${counts.create ?? 0} create, ${counts.update ?? 0} update, ` +
            `${counts.replace ?? 0} replace, ${counts.delete ?? 0} delete, ` +
            `${counts.read ?? 0} read`,
        );
        if (Array.isArray(value.resources) && value.resources.length) {
          const list = document.createElement('ul');
          for (const resource of value.resources.slice(0, 12)) {
            const item = document.createElement('li');
            item.textContent = resource.label ?? `${resource.action}: ${resource.address}`;
            list.append(item);
          }
          if (value.resources.length > 12) {
            const item = document.createElement('li');
            item.textContent = `…and ${value.resources.length - 12} more actions`;
            list.append(item);
          }
          output.append(list);
        }
        break;
      }
      case 'terraform-apply':
        appendText(output, 'Deployment', 'The reviewed saved plan was applied');
        break;
      case 'discovery':
        appendText(output, 'Resources discovered', value.resourceCount ?? 0);
        appendText(output, 'Manifest', value.partial ? 'Partial results' : 'Complete');
        break;
      case 'analysis':
        appendText(
          output,
          'Visibility candidates',
          Array.isArray(value.candidates) ? value.candidates.length : 0,
        );
        appendText(output, 'Missing telemetry', value.missingTelemetryMeans ?? 'unknown');
        break;
      case 'workflows':
        appendText(
          output,
          'Prepared workflows',
          Array.isArray(value.workflowIds) ? value.workflowIds.length : 0,
        );
        if (value.note) appendText(output, 'Important', value.note);
        break;
      case 'final-links':
        for (const [label, href] of [
          ['Open the Elastic cockpit', value.cockpit],
          ['Open the GCP project', value.cloudConsole],
        ]) {
          if (!href) continue;
          const link = document.createElement('a');
          link.href = href;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = label;
          output.append(link);
        }
        break;
      default:
        appendText(output, 'Status', 'Completed successfully');
    }
  }

  const advanced = document.createElement('details');
  advanced.className = 'advanced-output';
  const summary = document.createElement('summary');
  summary.textContent = 'Advanced: raw output';
  const raw = document.createElement('pre');
  raw.textContent = [
    ...(record.logs ?? []),
    record.result
      ? `Result JSON:\n${JSON.stringify(record.result, null, 2)}`
      : '',
  ]
    .filter(Boolean)
    .join('\n\n') || 'No raw command output was produced.';
  advanced.append(summary, raw);
  output.append(advanced);
  container.append(output);
}

async function mutateVisibility(url, body) {
  try {
    visibilityMessage.textContent = 'Updating the named candidate…';
    await api(url, { method: 'POST', body: JSON.stringify(body) });
    await loadVisibility();
  } catch (error) {
    visibilityMessage.textContent = error.message;
  }
}

function renderVisibility({ candidates, records }) {
  visibilityCandidates.replaceChildren();
  const byCandidate = new Map(
    records.map((record) => [record.candidateId, record]),
  );
  visibilityMessage.textContent = candidates.length
    ? `${candidates.length} named candidate(s) from the local analysis.`
    : 'The local analysis contains no visibility candidates.';
  for (const candidate of candidates) {
    const record = byCandidate.get(candidate.id);
    const card = document.createElement('article');
    card.className = 'candidate';
    const heading = document.createElement('h3');
    heading.textContent = candidate.name;
    const status = document.createElement('span');
    status.className = 'badge';
    status.textContent = record?.state ?? candidate.eligibility;
    const details = document.createElement('dl');
    detail(details, 'Candidate ID', candidate.id);
    detail(details, 'Target', candidate.resourceId);
    detail(details, 'Adapter', candidate.kind);
    detail(details, 'GCP cost', candidate.cost.gcp);
    detail(details, 'Elastic cost', candidate.cost.elastic);
    detail(details, 'Workload impact', candidate.workloadImpact);
    detail(details, 'Validation', candidate.validation);
    detail(details, 'Rollback', candidate.rollback);
    if (candidate.reason) detail(details, 'Unavailable because', candidate.reason);
    if (record?.reason) detail(details, 'Lifecycle note', record.reason);

    const approvals = document.createElement('div');
    approvals.className = 'approvals';
    const cost = document.createElement('input');
    cost.type = 'checkbox';
    const impact = document.createElement('input');
    impact.type = 'checkbox';
    for (const [input, text] of [
      [cost, 'I accept the stated GCP and Elastic cost'],
      [impact, 'I accept the stated workload impact'],
    ]) {
      const label = document.createElement('label');
      label.append(input, document.createTextNode(text));
      approvals.append(label);
    }

    const actions = document.createElement('div');
    actions.className = 'candidate-actions';
    const base = `/api/providers/gcp/visibility/candidates/${encodeURIComponent(candidate.id)}`;
    actions.append(
      actionButton(
        'Deploy and validate',
        () =>
          mutateVisibility(`${base}/deploy`, {
            costAccepted: cost.checked,
            impactAccepted: impact.checked,
          }),
        candidate.eligibility !== 'eligible' || record?.state === 'deployed',
      ),
      actionButton(
        'Rollback',
        () => mutateVisibility(`${base}/rollback`, {}),
        !record || ['rolled-back', 'skipped'].includes(record.state),
      ),
      actionButton('Skip', () => {
        const reason = window.prompt('Why are you skipping this named candidate?');
        if (reason?.trim()) void mutateVisibility(`${base}/skip`, { reason });
      }),
    );
    card.append(heading, status, details, approvals, actions);
    visibilityCandidates.append(card);
  }
}

async function loadVisibility() {
  try {
    renderVisibility(await api('/api/providers/gcp/visibility'));
  } catch (error) {
    visibilityCandidates.replaceChildren();
    visibilityMessage.textContent =
      error.message === 'Unexpected local server error'
        ? 'Run discovery and analysis before loading visibility candidates.'
        : error.message;
  }
}

projectInput.addEventListener('input', () => {
  localStorage.setItem('gcpProjectId', projectInput.value.trim());
  renderGuidedPath();
});

credentialsForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(credentialsForm));
  credentialsButton.disabled = true;
  credentialsButton.textContent = 'Saving…';
  credentialsStatus.className = 'form-status muted';
  credentialsStatus.textContent = 'Saving credentials to the owner-only local file…';
  try {
    const uploadedCredential = applicationCredentialsFile.files[0];
    if (uploadedCredential) {
      if (uploadedCredential.size > 65_536) {
        throw new Error('Google credential JSON must be 64 KiB or smaller');
      }
      values.applicationCredentialsJson = await uploadedCredential.text();
    }
    const status = await api('/api/credentials', {
      method: 'PUT',
      body: JSON.stringify(values),
    });
    const feedback = status.cloudConfigured && status.elasticConfigured
      ? `Credentials saved locally (${status.method}). Run Preflight to validate them.`
      : 'Credentials were saved, but setup is incomplete.';
    credentialsStatus.className = status.cloudConfigured && status.elasticConfigured
      ? 'form-status success'
      : 'form-status warning';
    credentialsStatus.textContent = feedback;
    credentialState = status;
    renderGuidedPath();
    message.textContent = feedback;
    credentialsForm.reset();
  } catch (error) {
    credentialsStatus.className = 'form-status failed';
    credentialsStatus.textContent = `Credentials were not saved: ${error.message}`;
  } finally {
    credentialsButton.disabled = false;
    credentialsButton.textContent = 'Save local credentials';
  }
});

document.querySelector('#cleanup-orphans').addEventListener('click', async () => {
  const confirmation = window.prompt(
    'Type CLEANUP ORPHANS to restore snapshots for locally managed, untracked adapters.',
  );
  if (confirmation !== 'CLEANUP ORPHANS') return;
  await mutateVisibility('/api/providers/gcp/visibility/orphans/cleanup', {
    confirmation,
  });
});

try {
  const bootstrap = await api('/api/bootstrap');
  csrfToken = bootstrap.csrfToken;
  credentialState = bootstrap.credentials;
  operationHistory = bootstrap.operations;
  if (credentialState.cloudConfigured && credentialState.elasticConfigured) {
    credentialsStatus.className = 'form-status success';
    credentialsStatus.textContent =
      `Credentials are saved locally (${credentialState.method}). Run Preflight to validate them.`;
  }
  renderGuidedPath();
  const latest = bootstrap.operations.find(
    (operation) => operation.projectId === projectInput.value.trim(),
  );
  if (latest) renderOperation(latest);
  await loadVisibility();
} catch (error) {
  state.textContent = 'failed';
  state.classList.add('failed');
  message.textContent = error.message;
}
