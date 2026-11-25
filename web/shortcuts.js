'use strict';
let shortcutDraft=null, shortcutsDirty=false, customShortcutDirty=false, shortcutOptions='';
const shortcutChecks=['show_browser','show_rdp','show_citrix','show_shutdown','show_restart','confirm_power','show_system_icons','show_panel'];
function markShortcutsDirty(){shortcutsDirty=true;$('shortcut-dirty').textContent='Alterações ainda não salvas. Clique em Salvar atalhos do grupo.';}
function resetCustomShortcut(){ customShortcutDirty=false;$('custom-shortcut-form').reset();$('custom-shortcut-form').elements.id.value='';$('custom-shortcut-title').textContent='Novo atalho'; }
function loadShortcutGroup(group){
  shortcutDraft=group?structuredClone(group):null;shortcutsDirty=false;$('shortcut-dirty').textContent='';
  $('shortcut-workspace').hidden=!group;
  $('shortcut-mode-hint').textContent=!group?'Crie um grupo em Grupos e perfis para configurar seus atalhos.':group.mode==='kiosk'?'Este grupo está em quiosque: o desktop e seus atalhos ficam ocultos. As escolhas serão usadas ao voltar ao modo desktop.':'Os agentes recebem estas escolhas após salvar. A imagem cliente precisa conter a versão atual do FreeThinClient.';
  if(!group)return;
  const form=$('shortcut-settings');form.reset();
  for(const key of shortcutChecks) if(group[key]!==undefined) form.elements[key].checked=!!group[key];
  for(const key of ['browser_title','rdp_title','citrix_title']) if(group[key])form.elements[key].value=group[key];
  shortcutDraft.shortcuts ||= [];resetCustomShortcut();renderCustomShortcuts();
}
function renderShortcutGroups(groups){
  const select=$('shortcut-group'), signature=JSON.stringify(groups.map(group=>[group.id,group.name]));
  if(signature!==shortcutOptions){
    const selected=select.value;shortcutOptions=signature;
    select.replaceChildren(...groups.map(group=>{const option=node('option','',group.name);option.value=group.id;return option;}));
    if(groups.some(group=>group.id===selected))select.value=selected;
    if(!select.value && groups.length)select.value=groups[0].id;
  }
  const group=groups.find(group=>group.id===select.value);
  if(!group || !shortcutsDirty && !customShortcutDirty && (!shortcutDraft || shortcutDraft.id!==group.id || shortcutDraft.revision!==group.revision))loadShortcutGroup(group);
}
function renderCustomShortcuts(){
  const list=shortcutDraft?.shortcuts || [];
  $('custom-shortcut-list').replaceChildren(...(list.length?list.map((item,index)=>{
    const row=node('article','shortcut-item'), icon=node('img','');icon.src='/assets/'+item.icon+'.svg';icon.alt='';
    const info=node('div','');info.append(node('h3','',item.name),node('p','muted',item.url));
    const actions=node('div','actions'), visible=node('input','');visible.type='checkbox';visible.checked=item.enabled!==false;
    visible.setAttribute('aria-label','Mostrar '+item.name);visible.addEventListener('change',()=>{item.enabled=visible.checked;markShortcutsDirty();});
    const edit=actionButton('Editar',()=>{const form=$('custom-shortcut-form');for(const key of ['id','name','url','icon'])form.elements[key].value=item[key];$('custom-shortcut-title').textContent='Editar '+item.name;form.elements.name.focus();});
    const remove=actionButton('Remover',()=>{list.splice(index,1);markShortcutsDirty();renderCustomShortcuts();});
    actions.append(visible,edit,remove);row.append(icon,info,actions);return row;
  }):[node('p','empty-state','Nenhum atalho adicional. Adicione um site abaixo.')]));
}
function initializeShortcutsUI(){
  $('shortcut-group').addEventListener('change',()=>{
    if((shortcutsDirty || customShortcutDirty) && !confirm('Descartar as alterações de atalhos ainda não salvas?')){$('shortcut-group').value=shortcutDraft.id;return;}
    loadShortcutGroup(fleetState.groups.find(group=>group.id===$('shortcut-group').value));
  });
  $('shortcut-settings').addEventListener('input',markShortcutsDirty);
  $('shortcut-settings').addEventListener('submit',async event=>{
    event.preventDefault();if(!shortcutDraft)return;
    if(customShortcutDirty)return notify('Adicione o atalho à lista ou limpe a edição antes de salvar o grupo.',true);
    const form=event.target, data={id:shortcutDraft.id,shortcuts:shortcutDraft.shortcuts};
    for(const key of shortcutChecks)data[key]=form.elements[key].checked;
    for(const key of ['browser_title','rdp_title','citrix_title'])data[key]=form.elements[key].value;
    try{await api('/api/groups/save',data);shortcutsDirty=false;await refresh();loadShortcutGroup(fleetState.groups.find(group=>group.id===data.id));notify('Atalhos e ações salvos para o grupo.');}catch(error){notify(error.message,true);}
  });
  $('custom-shortcut-form').addEventListener('input',()=>{customShortcutDirty=true;});
  $('custom-shortcut-form').addEventListener('submit',event=>{
    event.preventDefault();if(!shortcutDraft)return;
    const data=Object.fromEntries(new FormData(event.target)), list=shortcutDraft.shortcuts;
    const index=list.findIndex(item=>item.id===data.id);
    if(index<0 && list.length>=12)return notify('O grupo aceita até 12 atalhos adicionais.',true);
    if(!data.id)data.id=Array.from(crypto.getRandomValues(new Uint8Array(6)),byte=>byte.toString(16).padStart(2,'0')).join('');
    data.enabled=index<0?true:list[index].enabled;
    index<0?list.push(data):list.splice(index,1,data);
    markShortcutsDirty();renderCustomShortcuts();resetCustomShortcut();
  });
  $('cancel-shortcut').addEventListener('click',resetCustomShortcut);
  addEventListener('beforeunload',event=>{if(shortcutsDirty || customShortcutDirty){event.preventDefault();event.returnValue='';}});
}
