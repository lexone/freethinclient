const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web/remote-channel.js'),'utf8').replace('export default class','class');
const context=vm.createContext({setTimeout,Uint8Array,Error,btoa:s=>Buffer.from(s,'binary').toString('base64'),atob:s=>Buffer.from(s,'base64').toString('binary')});
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
  console.log('Remote channel passed: connection, binary frames, owned input buffer, safe retry and close');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
