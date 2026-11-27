"use strict";
let networkDraft=null,networkDirty=false,networkOptions='';
function loadNetworkGroup(group){
  networkDraft=group?structuredClone(group):null;networkDirty=false;
  $('network-dirty').textContent='';$('network-settings').hidden=!group;
  $('network-group-help').textContent=group?'As escolhas são aplicadas somente às máquinas vinculadas a este grupo.':'Crie um grupo em Grupos e perfis para configurar a rede.';
  if(!group)return;
  const form=$('network-settings');form.reset();
  form.elements.dns_override.checked=!!group.dns_override;
  form.elements.allow_network_settings.checked=!!group.allow_network_settings;
  for(const key of ['dns_servers','dns_search'])form.elements[key].value=Array.isArray(group[key])?group[key].join(', '):group[key] || '';
}
function renderNetworkGroups(groups){
  const select=$('network-group'),signature=JSON.stringify(groups.map(g=>[g.id,g.name]));
  if(signature!==networkOptions){
    networkOptions=signature;const old=select.value;
    select.replaceChildren(...groups.map(group=>{const option=node('option','',group.name);option.value=group.id;return option;}));
    if(groups.some(g=>g.id===old))select.value=old;
    if(!select.value && groups.length)select.value=groups[0].id;
  }
  const group=groups.find(g=>g.id===select.value);
  if(!group || !networkDirty && (!networkDraft || networkDraft.id!==group.id || networkDraft.revision!==group.revision))loadNetworkGroup(group);
  const devices=fleetState.devices.filter(d=>d.group_id===select.value);
  $('network-device-status').replaceChildren(...(devices.length?devices.map(device=>{
    const row=node('article','group-item'),state=device.dns_status || {};
    row.append(node('h3','',device.name+(device.ip?' · '+device.ip:'')),node('p',state.state==='error'?'amber':'muted',state.message || 'Aguardando um agente com suporte a DNS gerenciado.'),node('p','muted',(device.online?'Online':'Sem comunicação')+(state.timestamp?' · Último estado: '+new Date(state.timestamp*1000).toLocaleString('pt-BR'):'')));
    return row;
  }):[node('p','empty-state','Nenhuma máquina vinculada a este grupo.')]));
}
function initializeNetworkUI(){
  $('network-group').addEventListener('change',()=>{
    if(networkDirty && !confirm('Descartar alterações de rede ainda não salvas?')){$('network-group').value=networkDraft.id;return;}
    loadNetworkGroup(fleetState.groups.find(g=>g.id===$('network-group').value));renderNetworkGroups(fleetState.groups);
  });
  $('network-settings').addEventListener('input',()=>{networkDirty=true;$('network-dirty').textContent='Alterações ainda não salvas.';});
  $('network-settings').addEventListener('submit',async event=>{
    event.preventDefault();if(!networkDraft)return;
    const form=event.target,data={id:networkDraft.id,dns_override:form.elements.dns_override.checked,
      allow_network_settings:form.elements.allow_network_settings.checked,dns_servers:form.elements.dns_servers.value,dns_search:form.elements.dns_search.value};
    try{
      await api('/api/groups/save',data);networkDirty=false;await refresh();
      loadNetworkGroup(fleetState.groups.find(g=>g.id===data.id));notify('Rede e DNS salvos. Aguarde o resultado dos agentes abaixo.');
    }catch(error){notify(error.message,true);}
  });
  addEventListener('beforeunload',event=>{if(networkDirty){event.preventDefault();event.returnValue='';}});
}
