const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/remote-channel.js'),'utf8').replace('export default class','class');
const context=vm.createContext({console:{error(){}},setTimeout,Uint8Array,Error,btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary')});
vm.runInContext(source+'\nglobalThis.Channel=RemoteChannel',context);
async function main(){
  const calls=[];let failed=false;let opened=0;let received=0;let finished;
  const done=new Promise(resolve=>finished=resolve);
  const channel=new context.Channel('test',async(path,payload)=>{
    calls.push([path,JSON.parse(JSON.stringify(payload))]);
    if(path.endsWith('/stop'))return {ok:true};
    if(payload.seq===1&&!failed){failed=true;throw new Error('Simulated lost response');}
    if(payload.seq===1)return {state:'connected',data:Buffer.from('RFB bytes').toString('base64')};
    assert.equal(Buffer.from(payload.data,'base64').toString(),'keyboard');
    setTimeout(()=>{channel.close();finished();},0);
    return {state:'connected',data:''};
  },()=>{});
  channel.onopen=()=>{opened++;const bytes=Uint8Array.from(Buffer.from('keyboard'));channel.send(bytes);bytes.fill(0);};
  channel.onmessage=event=>{received++;assert.equal(Buffer.from(event.data).toString(),'RFB bytes');};
  await Promise.race([done,new Promise((_,reject)=>setTimeout(()=>reject(Error('Timeout')),3000))]);
  assert.equal(opened,1);assert.equal(received,1);assert.equal(channel.readyState,3);
  assert.deepEqual(calls[0],calls[1],'Retry uses identical sequence and bytes');
  assert(calls.some(([path])=>path==='/api/remote/stop'));
  let failedClose;
  const failedDone=new Promise(resolve=>failedClose=resolve);
  const bad=new context.Channel('old-image',async path=>path.endsWith('/stop')?{}:{state:'error',message:'Atualize os componentes do cliente e reinicie o PC.'},()=>{});
  bad.onclose=event=>{assert.equal(event.wasClean,false);assert.match(event.reason,/Atualize os componentes/);failedClose();};
  await failedDone;
  assert.match(bad.failure,/Atualize os componentes/);
  let decoderClosed;
  const decoderDone=new Promise(resolve=>decoderClosed=resolve);
  const decoder=new context.Channel('decoder',async path=>path.endsWith('/stop')?{}:{state:'connected',data:Buffer.from('RFB').toString('base64')},()=>{});
  decoder.onmessage=()=>{throw Error('decoder fixture');};
  decoder.onclose=()=>decoderClosed();
  await decoderDone;
  assert.match(decoder.failure,/decoder fixture/,'A decoder exception must close with a visible failure');
  assert.equal(decoder.receivedBytes,3);
  assert.equal(decoder.polls,1);

  // Exercise the actual console controller; a disconnect must not hide the error.
  const nodes=new Map();
  const element=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',dataset:{},listeners:{},
    addEventListener(event,fn){this.listeners[event]=fn;},replaceChildren(){},showModal(){},close(){this.listeners.close?.();}});return nodes.get(id);};
  class FakeRFB {
    constructor(){this.listeners={};}
    addEventListener(event,fn){this.listeners[event]=fn;}
    disconnect(){if(this.closed)return;this.closed=true;this.listeners.disconnect?.({detail:{clean:true}});}
  }
  class FakeChannel {constructor(){this.failure='';}close(){}}
  const ui=vm.createContext({setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){},document:{getElementById:element},window:{addEventListener(){},remoteApi:async()=>({id:'session',password:'fixture'})},RFB:FakeRFB,RemoteChannel:FakeChannel});
  const controller=fs.readFileSync(path.join(__dirname,'../web/remote.js'),'utf8').replace(/^import .*;\r?\n/gm,'');
  vm.runInContext(controller,ui);
  await ui.window.openRemoteConsole({id:'pc',name:'Test'});
  await element('remote-start').listeners.click();
  vm.runInContext("channel.failure='Atualize a imagem e reinicie o PC.';rfb.disconnect();",ui);
  assert.equal(element('remote-status').textContent,'Atualize a imagem e reinicie o PC.');
  console.log('Remote channel passed: connection, binary frames, owned input buffer, safe retry and close');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
