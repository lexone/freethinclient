import RFB from './vendor/novnc/core/rfb.js';
import RemoteChannel from './remote-channel.js';

let rfb, channel, session;
const dialog=document.getElementById('remote-dialog');
const status=document.getElementById('remote-status');
const screen=document.getElementById('remote-screen');
const setStatus=text=>{status.textContent=text;};
let failure='';

function stop() {
  const previous=rfb, transport=channel;rfb=null;channel=null;
  if(transport?.failure)failure=transport.failure;
  previous?.disconnect();transport?.close();
  document.getElementById('remote-control').disabled=false;
  session=null;screen.replaceChildren();
}

window.openRemoteConsole=async device=>{
  stop();
  failure='';
  document.getElementById('remote-title').textContent='Console de '+device.name;
  document.getElementById('remote-control').checked=false;
  document.getElementById('remote-start').disabled=false;
  dialog.dataset.device=device.id;
  setStatus('Somente visualizar está selecionado. Cada sessão dura até 10 minutos.');
  dialog.showModal();
};

document.getElementById('remote-start').addEventListener('click',async()=>{
  const button=document.getElementById('remote-start');button.disabled=true;
  try {
    failure='';
    const control=document.getElementById('remote-control').checked;
    document.getElementById('remote-control').disabled=true;
    session=await window.remoteApi('/api/remote/start',{device:dialog.dataset.device,control});
    setStatus('Aguardando o agente. O cliente precisa da imagem atualizada.');
    channel=new RemoteChannel(session.id,window.remoteApi,setStatus);
    rfb=new RFB(screen,channel,{credentials:{password:session.password}});
    rfb.viewOnly=!control;rfb.scaleViewport=true;rfb.resizeSession=false;
    rfb.qualityLevel=5;rfb.compressionLevel=3;
    rfb.addEventListener('connect',()=>setStatus(control?'Conectado — controle habilitado':'Conectado — somente visualizar'));
    rfb.addEventListener('disconnect',event=>{
      const message=failure||channel?.failure||(event.detail.clean?'Console desconectado.':'A conexão VNC foi interrompida antes de concluir. Confira se a imagem cliente foi atualizada e o PC reiniciado.');
      stop();setStatus(message);button.disabled=false;
    });
    rfb.addEventListener('securityfailure',()=>{failure='Falha na autenticação do console. Abra uma nova sessão.';stop();setStatus(failure);button.disabled=false;});
  } catch(error){failure=error.message;stop();setStatus(failure);button.disabled=false;}
});
document.getElementById('remote-close').addEventListener('click',()=>dialog.close());
dialog.addEventListener('close',stop);
document.getElementById('remote-fullscreen').addEventListener('click',()=>{
  if(document.fullscreenElement)document.exitFullscreen();else dialog.requestFullscreen().catch(error=>setStatus(error.message));
});
window.addEventListener('pagehide',stop);
