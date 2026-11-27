import RFB from './vendor/novnc/core/rfb.js';
import RemoteChannel from './remote-channel.js';

let rfb, channel, session;
const dialog=document.getElementById('remote-dialog');
const status=document.getElementById('remote-status');
const screen=document.getElementById('remote-screen');
const setStatus=text=>{status.textContent=text;};
let failure='';
let vncConnected=false, diagnosticsTimer=null, handshakeTimer=null;

function renderDiagnostics() {
  const detail=document.getElementById('remote-detail');
  if(!detail||!channel)return;
  const stages={ProtocolVersion:'versão do protocolo',Security:'método de autenticação',Authentication:'autenticação',SecurityResult:'resultado da autenticação',ServerInitialisation:'inicialização da tela'};
  const stage=vncConnected?'sessão VNC negociada':stages[rfb?._rfbInitState]||'aguardando protocolo';
  const canvas=screen.querySelector?.('canvas');
  detail.textContent=`Recebidos: ${(channel.receivedBytes/1024).toFixed(1)} KiB · Enviados: ${channel.sentBytes} bytes · ${stage}`+(canvas?.width?` · Tela: ${canvas.width} × ${canvas.height}`:'');
}

function stop() {
  clearInterval(diagnosticsTimer);clearTimeout(handshakeTimer);diagnosticsTimer=null;handshakeTimer=null;
  const previous=rfb, transport=channel;rfb=null;channel=null;
  if(transport?.failure)failure=transport.failure;
  previous?.disconnect();transport?.close();
  document.getElementById('remote-control').disabled=false;
  session=null;screen.replaceChildren();
}

window.openRemoteConsole=async device=>{
  stop();
  failure='';
  vncConnected=false;
  const detail=document.getElementById('remote-detail');if(detail)detail.textContent='';
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
    vncConnected=false;
    const control=document.getElementById('remote-control').checked;
    document.getElementById('remote-control').disabled=true;
    session=await window.remoteApi('/api/remote/start',{device:dialog.dataset.device,control});
    setStatus('Aguardando o agente. O cliente precisa da imagem atualizada.');
    channel=new RemoteChannel(session.id,window.remoteApi,message=>{if(!vncConnected)setStatus(message);renderDiagnostics();});
    rfb=new RFB(screen,channel,{credentials:{password:session.password}});
    rfb.viewOnly=!control;rfb.scaleViewport=true;rfb.resizeSession=false;
    rfb.qualityLevel=5;rfb.compressionLevel=3;
    rfb.addEventListener('connect',()=>{vncConnected=true;clearTimeout(handshakeTimer);setStatus(control?'Sessão VNC conectada — controle habilitado':'Sessão VNC conectada — somente visualizar');renderDiagnostics();});
    rfb.addEventListener('disconnect',event=>{
      const message=failure||channel?.failure||(event.detail.clean?'Console desconectado.':'A conexão VNC foi interrompida antes de concluir. Confira se a imagem cliente foi atualizada e o PC reiniciado.');
      stop();setStatus(message);button.disabled=false;
    });
    rfb.addEventListener('securityfailure',()=>{failure='Falha na autenticação do console. Abra uma nova sessão.';stop();setStatus(failure);button.disabled=false;});
    diagnosticsTimer=setInterval(renderDiagnostics,1000);
    handshakeTimer=setTimeout(()=>{
      if(vncConnected||!channel)return;
      renderDiagnostics();failure='O agente respondeu, mas a negociação VNC não terminou em 30 segundos. Confira o diagnóstico abaixo e o Console do navegador (F12).';
      stop();setStatus(failure);button.disabled=false;
    },30000);
  } catch(error){failure=error.message;stop();setStatus(failure);button.disabled=false;}
});
document.getElementById('remote-close').addEventListener('click',()=>dialog.close());
dialog.addEventListener('close',stop);
document.getElementById('remote-fullscreen').addEventListener('click',()=>{
  if(document.fullscreenElement)document.exitFullscreen();else dialog.requestFullscreen().catch(error=>setStatus(error.message));
});
window.addEventListener('pagehide',stop);
