'use strict';
let imageTaskBusy=false, imageWorkerReady=false, lastImageState='';
const imageStates={idle:'Pronto para consultar',queued:'Na fila',preparing:'Preparando imagem',updating:'Atualizando pacotes',packing:'Compactando imagem',publishing:'Publicando imagem',done:'Tarefa concluída',error:'A tarefa falhou'};
function renderImages(status) {
  imageWorkerReady=!!status.worker_ready;
  imageTaskBusy=!!status.queued || ['preparing','updating','packing','publishing'].includes(status.state);
  const state=status.queued && !['preparing','updating','packing','publishing'].includes(status.state)?'queued':status.state;
  const title=imageStates[state] || state;
  if ($('image-job-title').textContent!==title) $('image-job-title').textContent=title;
  $('image-job-message').textContent=imageWorkerReady?(state==='queued'?'O serviço verifica as solicitações a cada 15 segundos.':status.message || ''):'O componente de manutenção de imagem ainda precisa ser instalado neste servidor.';
  $('image-job-time').textContent=status.timestamp?'Última atualização: '+new Date(status.timestamp*1000).toLocaleString('pt-BR')+(status.actor?' · solicitado por '+status.actor:''):'';
  $('image-job-progress').value=state==='queued'?0:status.step || 0;
  $('image-job-log').textContent=status.log || 'Aguardando saída da tarefa.';
  const versions=status.versions;
  $('image-versions').replaceChildren(...[['linux-image-amd64','Kernel Linux'],['chromium','Chromium'],['google-chrome-stable','Google Chrome'],['icaclient','Citrix Workspace']].map(([key,label])=>{
    const item=node('article','image-version');item.append(node('span','muted',label),node('strong','',versions?(versions[key] || 'Não instalado'):'Ainda não consultado'));return item;
  }));
  for(const button of document.querySelectorAll('[data-image-action],#image-inspect,#image-citrix')) button.disabled=imageTaskBusy || !imageWorkerReady;
  $('image-rollback').disabled=imageTaskBusy || !imageWorkerReady || !status.rollback_available;
  $('image-manager').setAttribute('aria-busy',String(imageTaskBusy));
  if(lastImageState && lastImageState!==state && state==='done') notify(status.message || 'Tarefa da imagem concluída.');
  lastImageState=state;
}
async function queueImage(data) {
  if(imageTaskBusy) return;
  const messages={client:'Aplicar os componentes FreeThinClient atuais à imagem dos PCs?',linux:'Atualizar os pacotes e kernel da imagem Debian 12?',chromium:'Atualizar o Chromium da imagem?',chrome:'Instalar ou atualizar o Google Chrome estável na imagem? Ele será o navegador preferido dos grupos.',citrix:'Instalar o pacote Citrix informado na imagem?',rollback:'Restaurar a imagem anterior para os próximos boots?'};
  if(data.action!=='inspect' && !confirm(messages[data.action]+' Os PCs só receberão a mudança após reiniciar.')) return;
  try {
    await api('/api/images/jobs',data); imageTaskBusy=true;
    renderImages({state:'queued',queued:true,worker_ready:true,step:0,message:'Solicitação enviada.'});
    notify('Tarefa solicitada. Acompanhe as etapas e o log nesta tela.');await refresh();
  } catch(error){notify(error.message,true);await refresh();}
}
function initializeImagesUI() {
  $('open-image-manager').addEventListener('click',()=>{
    const manager=$('image-manager');
    if(manager.hidden) return notify('Entre como administrador e atualize o painel para disponibilizar esta área.',true);
    manager.scrollIntoView({behavior:'smooth',block:'start'});
  });
  $('image-inspect').addEventListener('click',()=>queueImage({action:'inspect'}));
  $('image-rollback').addEventListener('click',()=>queueImage({action:'rollback'}));
  for(const button of document.querySelectorAll('[data-image-action]')) button.addEventListener('click',()=>queueImage({action:button.dataset.imageAction}));
  $('citrix-update-form').addEventListener('submit',event=>{event.preventDefault();queueImage({action:'citrix',...Object.fromEntries(new FormData(event.target))});});
}
