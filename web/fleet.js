'use strict';
let fleetState = {groups: [], devices: []}, groupDirty = false, groupSignature = '';
const pages = {
  overview: ['Seu ambiente, em um só lugar.', 'Dispositivos, perfis e conexões sob seu controle.'],
  machines: ['Cada máquina, no lugar certo.', 'Aprove os dispositivos e acompanhe a comunicação com o agente.'],
  groups: ['Um perfil. Todo o grupo.', 'Defina como as máquinas iniciam e o que seus usuários podem abrir.'],
  boot: ['O começo de cada workspace.', 'Imagem Linux e arquivos para inicializar seus thin clients.'],
  desktop: ['Um espaço com a sua identidade.', 'Desktop azul, ícones claros e o wallpaper da sua organização.'],
  updates: ['Seu ambiente em dia.', 'Atualizações assinadas com backup e recuperação.'],
  audit: ['Tudo o que aconteceu.', 'Acompanhe os registros administrativos do ambiente.']
};
const modeNames = {desktop:'Desktop', browser:'Navegador', kiosk:'Quiosque', citrix:'Citrix', rdp:'RDP'};
function route() {
  const key = location.hash.slice(1) in pages ? location.hash.slice(1) : 'overview';
  for (const panel of document.querySelectorAll('[data-page]')) panel.hidden = panel.dataset.page !== key;
  for (const link of document.querySelectorAll('[role=tab]')) {const active = link.hash === '#' + key; link.setAttribute('aria-selected', String(active)); link.tabIndex = active ? 0 : -1;}
  $('page-title').textContent = authenticated ? pages[key][0] : 'Acesse seu ambiente.';
  $('page-description').textContent = authenticated ? pages[key][1] : 'Entre para administrar seus thin clients.';
}
addEventListener('hashchange', () => {route(); requestAnimationFrame(()=>scrollTo(0,0));});
function node(tag, className, content) {const element = document.createElement(tag); if (className) element.className = className; if (content !== undefined) element.textContent = content; return element;}
function actionButton(label, handler, secondary = true) {const button = node('button', secondary ? 'secondary' : '', label); button.type = 'button'; button.addEventListener('click', handler); return button;}
function resetGroup(group = {}) {
  const form = $('group-form'); form.reset();
  for (const [key, value] of Object.entries(group)) {const input = form.elements.namedItem(key); if (input) input.type === 'checkbox' ? input.checked = value : input.value = value;}
  form.elements.id.value = group.id || '';
  $('group-editor-title').textContent = group.id ? 'Editar ' + group.name : 'Novo grupo';
  groupDirty = false; $('group-dirty').textContent = '';
}
function renderGroups() {
  const signature = JSON.stringify(fleetState.groups);
  if (signature === groupSignature) return; groupSignature = signature;
  const rows = fleetState.groups.map(group => {
    const card = node('article','group-item');
    card.append(node('h3','',group.name), node('p','muted',group.description || 'Perfil de máquinas'), node('span','pill',modeNames[group.mode] + ' · ' + group.boot_type.toUpperCase()));
    const actions = node('div','actions');
    actions.append(actionButton('Editar', () => {
      if (groupDirty && !confirm('Descartar as alterações do formulário para abrir outro grupo?')) return;
      resetGroup(group); $('group-form').elements.name.focus();
    }), actionButton('Excluir', async () => {
      if (!confirm('Excluir o grupo ' + group.name + '? Grupos com máquinas precisam ser esvaziados antes.')) return;
      try {await api('/api/groups/delete',{id:group.id}); if ($('group-form').elements.id.value === group.id) resetGroup(); await refresh(); notify('Grupo excluído.');} catch(error) {notify(error.message,true);}
    })); card.append(actions); return card;
  });
  $('group-list').replaceChildren(...(rows.length ? rows : [node('p','empty-state','Nenhum grupo ainda. Crie um perfil ao lado para começar.')]));
}
function renderDevices(force = false) {
  if (!force && $('device-list').contains(document.activeElement)) return;
  const query = $('device-search').value.trim().toLowerCase();
  const rows = fleetState.devices.filter(device => [device.name,device.mac,device.ip || ''].some(value => value.toLowerCase().includes(query))).map(device => {
    const row = node('article','device-row'), info = node('div','device-info');
    info.append(node('h3','',device.name),node('p','mono',device.mac + (device.ip ? ' · ' + device.ip : '')),
      node('span',device.approved ? (device.online ? 'status online' : 'status') : 'status pending', !device.approved ? 'Aguardando aprovação' : device.online ? 'Online' : 'Sem comunicação'));
    if (device.command) info.append(node('p','muted','Aguardando agente: ' + device.command));
    row.append(info);
    const controls = node('div','device-controls'), select = node('select',''); select.setAttribute('aria-label','Grupo de ' + device.name);
    const placeholder = node('option','','Selecione um grupo'); placeholder.value=''; select.append(placeholder);
    for (const group of fleetState.groups) {const option=node('option','',group.name);option.value=group.id;select.append(option);} select.value = device.group_id || '';
    controls.append(select, actionButton(device.approved ? 'Mover / aplicar' : 'Aprovar', async () => {
      try {await api('/api/devices/assign',{id:device.id,group_id:select.value});await refresh();notify('Perfil liberado. O agente recebe as configurações na próxima comunicação.');}catch(error){notify(error.message,true);}
    },false));
    if (device.approved) for (const [action,label] of [['reapply','Reaplicar'],['reboot','Reiniciar'],['poweroff','Desligar']]) {
      controls.append(actionButton(label, async () => {
        if (action !== 'reapply' && !confirm(label + ' a máquina ' + device.name + '? A sessão do usuário será interrompida.')) return;
        try {await api('/api/devices/command',{id:device.id,action});await refresh();notify('Comando enviado. Aguarde a confirmação do agente.');} catch(error) {notify(error.message,true);}
      }));
    }
    controls.append(actionButton('Remover cadastro',async()=>{
      if(!confirm('Remover ' + device.name + ' e revogar sua credencial? O agente precisará de novo cadastro.')) return;
      try{await api('/api/devices/delete',{id:device.id});await refresh();notify('Cadastro removido.');}catch(error){notify(error.message,true);}
    })); row.append(controls); return row;
  });
  $('device-list').replaceChildren(...(rows.length ? rows : [node('div','empty-state',query ? 'Nenhuma máquina corresponde à busca.' : 'Aguardando o primeiro PC. Inicie a imagem e configure o agente para solicitar o cadastro.')]));
}
function renderFleet(fleet) {
  fleetState = fleet; renderGroups(); renderDevices();
  $('count-devices').textContent = fleet.devices.length; $('count-online').textContent = fleet.devices.filter(item=>item.online).length; $('count-groups').textContent = fleet.groups.length;
  $('pending-count').textContent = fleet.devices.filter(item=>!item.approved).length + ' pendentes';
  $('boot-files').replaceChildren(...Object.entries(fleet.boot.files).map(([name,exists])=>{const item=node('div','boot-file');item.append(node('span','mono',name),node('span',exists?'status online':'status pending',exists?'Disponível':'Ainda não gerado'));return item;}));
  $('boot-message').textContent = (fleet.boot.image_available ? 'Arquivos disponíveis no servidor. ' : 'A imagem ainda precisa ser gerada e publicada no servidor. ') + fleet.boot.message;
}
function initializeFleetUI() {
  document.querySelector('[role=tablist]').addEventListener('keydown', event => {
    const links = [...document.querySelectorAll('[role=tab]')], index = links.indexOf(event.target);
    if (index < 0 || !['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? links.length - 1 : (index + (['ArrowUp','ArrowLeft'].includes(event.key) ? -1 : 1) + links.length) % links.length;
    location.hash = links[next].hash; links[next].focus();
  });
  $('device-search').addEventListener('input',()=>renderDevices(true));
  for (const id of ['new-group','cancel-group']) $(id).addEventListener('click',()=>{if(!groupDirty || confirm('Descartar as alterações do formulário?')) resetGroup();});
  $('group-form').addEventListener('input',()=>{groupDirty=true;$('group-dirty').textContent='Você tem alterações ainda não salvas.';});
  $('group-form').addEventListener('submit',async event=>{
    event.preventDefault();const data=Object.fromEntries(new FormData(event.target));
    for(const key of ['reconnect','lock_wallpaper','allow_usb','mac_reenroll']) data[key]=event.target.elements[key].checked;
    try{const result=await api('/api/groups/save',data);groupDirty=false;await refresh();resetGroup(fleetState.groups.find(group=>group.id===result.id));notify('Grupo salvo. Os agentes aprovados recebem o perfil na próxima comunicação.');}catch(error){notify(error.message,true);}
  });
  addEventListener('beforeunload',event=>{if(groupDirty){event.preventDefault();event.returnValue='';}});
  route();
}
