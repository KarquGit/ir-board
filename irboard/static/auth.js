const form = document.querySelector('#pair-form');
const input = document.querySelector('#pair-code');
const button = document.querySelector('#pair-submit');
const status = document.querySelector('#pair-status');
let busy = false;

async function pair(code) {
  if (busy) return;
  busy = true;
  button.disabled = true;
  status.textContent = 'Pairing this device…';
  try {
    const response = await fetch('/api/pair', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({code}), signal:AbortSignal.timeout(6500),
    });
    const result = await response.json();
    if (!response.ok) throw Error(result.error || 'Could not pair this device.');
    location.replace('/');
  } catch (error) {
    status.textContent = error.name === 'TimeoutError' ?
      'No response. Check the connection, then use a fresh code from the computer.' : error.message;
    input.value = '';
    input.focus();
  } finally {
    busy = false;
    button.disabled = false;
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  if (form.reportValidity()) pair(input.value);
});
const fragment = new URLSearchParams(location.hash.slice(1));
const code = fragment.get('pair');
// Remove single-use QR credentials before loading any other page.
if (location.hash) history.replaceState(null, '', location.pathname);
if (code) pair(code);
else input.focus();
