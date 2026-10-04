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
projectInput.value = localStorage.getItem('gcpProjectId') ?? '';

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

try {
  const bootstrap = await api('/api/bootstrap');
  csrfToken = bootstrap.csrfToken;
  const latest = bootstrap.operations[0];
  if (latest) renderOperation(latest);
} catch (error) {
  state.textContent = 'failed';
  state.classList.add('failed');
  message.textContent = error.message;
}
