'use strict';
let csrf = '', availableVersion = '', authenticated = false, lastUpdate = '';
const $ = id => document.getElementById(id);
function notify(message, error = false) { $('notice').textContent = message; $('notice').className = error ? 'error' : ''; }
async function api(path, data) {
  const response = await fetch(path, {method: data ? 'POST' : 'GET', headers: data ? {'Content-Type': 'application/json', 'X-CSRF-Token': csrf} : {}, body: data ? JSON.stringify(data) : undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
function showLogin() { authenticated = false; $('dashboard').hidden = true; $('logout').hidden = true; $('login').hidden = false; route(); }
function renderUpdate(update) {
  const labels = {idle:'Nenhuma consulta realizada.', checking:'Consultando e verificando a assinatura…', available:'Nova versão assinada disponível', current:'Você já está na versão disponível ou em uma versão superior.', downloading:'Baixando e validando o pacote…', applying:'Aplicando atualização. O painel pode ficar indisponível por alguns segundos.', updated:'Atualização concluída e serviço validado.', rolled_back:'A atualização falhou. A versão anterior foi restaurada.', error:'Não foi possível concluir a atualização.'};
  $('update-status').textContent = [labels[update.state] || update.state, update.version ? `Versão: ${update.version}` : '', update.message || ''].filter(Boolean).join(' ');
  availableVersion = update.state === 'available' && update.signature_valid ? update.version : '';
  $('apply-update').disabled = !availableVersion;
  $('check-update').disabled = ['checking','downloading','applying'].includes(update.state);
}
async function refresh(initial = false) {
  try {
    const [state, fleet] = await Promise.all([api('/api/state'),api('/api/fleet')]); csrf = state.csrf; authenticated = true;
    $('login').hidden = true; $('dashboard').hidden = false; $('logout').hidden = false;
    $('version').textContent = `v${state.version}`; $('installed-version').textContent = `Instalada: ${state.version}`; $('repository').textContent = state.repository;
    if (initial) {
      for (const [key, value] of Object.entries(state.profile)) {const input = $('profile-form').elements.namedItem(key); if (input) input.type === 'checkbox' ? input.checked = value : input.value = value;}
      if (state.wallpaper) { $('wallpaper-preview').src = '/api/wallpaper'; $('wallpaper-preview').hidden = false; $('wallpaper-empty').hidden = true; }
    }
    renderUpdate(state.update);
    renderFleet(fleet); route();
    $('events').replaceChildren(...state.events.map(event => {const li = document.createElement('li'); const time = document.createElement('time');time.textContent = new Date(event.ts * 1000).toLocaleString('pt-BR');li.append(time, document.createTextNode(event.action));return li;}));
    if (lastUpdate === 'applying' && state.update.state === 'updated') notify('Atualização concluída. Recarregue a página para carregar a nova interface.');
    lastUpdate = state.update.state;
  } catch (error) { if (initial) showLogin(); else notify('Reconectando ao painel… Se a sessão expirou, entre novamente.'); }
}
$('login-form').addEventListener('submit', async event => {event.preventDefault(); try {const data = Object.fromEntries(new FormData(event.target));const result = await api('/api/login', data);csrf = result.csrf;event.target.elements.password.value = '';notify('');await refresh(true);} catch(error) {notify(error.message, true);} });
$('logout').addEventListener('click', async () => {try {await api('/api/logout', {});showLogin();notify('Sessão encerrada.');}catch(error){notify(error.message,true);} });
$('profile-form').addEventListener('submit', async event => {event.preventDefault(); const data = Object.fromEntries(new FormData(event.target));try {await api('/api/profile', data);notify('Identificação salva. Configure as conexões na aba Grupos e perfis.');await refresh();}catch(error){notify(error.message,true);} });
$('wallpaper-file').addEventListener('change', async event => {const file = event.target.files[0];if (!file) return;if (file.size > 5 * 1024 * 1024) return notify('Escolha uma imagem de até 5 MB.',true);const reader = new FileReader();reader.onload = async () => {try {await api('/api/wallpaper', {data:String(reader.result).split(',')[1]});$('wallpaper-preview').src = '/api/wallpaper?t=' + Date.now();$('wallpaper-preview').hidden = false;$('wallpaper-empty').hidden = true;notify('Wallpaper salvo no servidor.');}catch(error){notify(error.message,true);}};reader.readAsDataURL(file);});
$('check-update').addEventListener('click', async () => {try {await api('/api/update/check', {});$('check-update').disabled = true;notify('Consulta agendada. O serviço responde em até 15 segundos.');}catch(error){notify(error.message,true);} });
$('apply-update').addEventListener('click', async () => {if (!availableVersion || !window.confirm(`Instalar a versão ${availableVersion}? Será feito backup e haverá uma breve interrupção do painel.`)) return;try {await api('/api/update/apply', {version:availableVersion});$('apply-update').disabled = true;notify('Atualização solicitada. Aguarde o resultado.');}catch(error){notify(error.message,true);} });
initializeFleetUI();
refresh(true);
setInterval(() => {if (authenticated) refresh();}, 5000);
