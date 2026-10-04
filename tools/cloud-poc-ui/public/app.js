const steps = [
  ['preflight', 'Preflight'],
  ['terraform-init', 'Initialize Terraform'],
  ['terraform-plan', 'Review saved plan'],
  ['terraform-apply', 'Apply saved plan'],
  ['discovery', 'Discover GCP'],
  ['analysis', 'Analyze coverage'],
  ['workflows', 'Run workflows'],
  ['final-links', 'Open final links'],
];

let csrfToken = '';
let activeEvents;
const stepContainer = document.querySelector('#steps');
const state = document.querySelector('#state');
const progress = document.querySelector('#progress');
const message = document.querySelector('#message');
const logs = document.querySelector('#logs');
const result = document.querySelector('#result');
const projectInput = document.querySelector('#projectId');
const visibilityCandidates = document.querySelector('#visibility-candidates');
const visibilityMessage = document.querySelector('#visibility-message');
projectInput.value = localStorage.getItem('gcpProjectId') ?? '';
let lastAnalysisLoaded;

function setButtonsDisabled(disabled) {
  document.querySelectorAll('#steps button').forEach((button) => {
    button.disabled = disabled;
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

for (const [operation, label] of steps) {
  const button = document.createElement('button');
  button.textContent = label;
  button.classList.toggle('primary', operation === 'preflight');
  button.addEventListener('click', async () => {
    const projectId = projectInput.value.trim();
    if (!projectId) {
      message.textContent = 'Enter the named GCP project ID first.';
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
  });
  stepContainer.append(button);
}

document.querySelector('#credentials').addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const status = await api('/api/credentials', {
      method: 'PUT',
      body: JSON.stringify(values),
    });
    message.textContent = status.cloudConfigured && status.elasticConfigured
      ? `Local credentials saved (${status.method}).`
      : 'Credential setup is incomplete.';
    event.currentTarget.reset();
  } catch (error) {
    state.textContent = 'failed';
    state.classList.add('failed');
    message.textContent = error.message;
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
  const latest = bootstrap.operations[0];
  if (latest) renderOperation(latest);
  await loadVisibility();
} catch (error) {
  state.textContent = 'failed';
  state.classList.add('failed');
  message.textContent = error.message;
}
