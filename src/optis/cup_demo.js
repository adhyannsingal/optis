/* Mock workflow in the existing /camera bench. Tokens stay in page memory. */
(() => {
  const status = document.querySelector('#cup-status');
  const progress = document.querySelector('#cup-progress');
  const token = () => document.querySelector('input[name="token"]').value.trim();
  const spotter = () => document.querySelector('#cup-spotter-token').value.trim();
  let polling = false;
  async function call(path, body, authority = token()) {
    const response = await fetch(path, {method: body ? 'POST' : 'GET', cache: 'no-store',
      headers: {'Authorization': 'Bearer ' + authority, ...(body ? {'Content-Type': 'application/json'} : {})},
      ...(body ? {body: JSON.stringify(body)} : {})});
    if (!response.ok) throw new Error((await response.json()).detail || 'Simulation unavailable.');
    return response.json();
  }
  function report(result) { status.textContent = result.text; }
  async function poll() {
    if (polling || !token()) return;
    polling = true;
    try {
      const result = await call('/v1/cup-demo');
      const s = result.status;
      status.textContent = `SIMULATION · ${s.state} · ${s.stage || 'no stage'} · ${s.code || ''} · task: ${s.task_id || 'none'}`;
      progress.textContent = result.events.slice(-14).map(e =>
        `${e.state} | ${e.stage || '-'} | ${e.code || '-'} | ${e.task_id || '-'}`).join('\n');
    } catch (error) { status.textContent = error.message; }
    finally { polling = false; }
  }
  document.querySelector('#cup-request').addEventListener('submit', async event => {
    event.preventDefault();
    const text = new FormData(event.target).get('text').trim();
    try { report(await call('/v1/cup-demo/request', {text, request_id: crypto.randomUUID()})); }
    catch (error) { status.textContent = error.message; }
  });
  document.querySelector('#cup-stop').addEventListener('click', async () => {
    try { report(await call('/v1/intent', {request_id: crypto.randomUUID(), kind: 'stop'})); }
    catch (error) { status.textContent = error.message; }
  });
  for (const button of document.querySelectorAll('[data-cup-action]')) {
    button.addEventListener('click', async () => {
      try { report(await call('/v1/cup-demo/spotter', {action: button.dataset.cupAction}, spotter())); }
      catch (error) { status.textContent = error.message; }
    });
  }
  document.querySelector('#cup-approval').addEventListener('submit', async event => {
    event.preventDefault();
    const task_id = new FormData(event.target).get('task_id').trim();
    try { report(await call('/v1/cup-demo/spotter', {action: 'approve', task_id}, spotter())); }
    catch (error) { status.textContent = error.message; }
  });
  document.querySelector('#cup-scenario').addEventListener('change', async event => {
    try { report(await call('/v1/cup-demo/scenario', {scenario: event.target.value}, spotter())); }
    catch (error) { status.textContent = error.message; }
  });
  setInterval(poll, 300);
})();
