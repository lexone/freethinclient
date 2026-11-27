// Exercise refresh races, failures and recovery using the shipped browser scripts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {textContent:'', dataset:{}, hidden:false,
    replaceChildren(...children){this.children=children;},
    setAttribute(key,value){this[key]=value;}, elements:{namedItem(){return null;}}});
  return elements.get(id);
};
let network, calls=0;
const context = vm.createContext({
  console, setTimeout, clearTimeout, AbortController, Date,
  addEventListener(){}, location:{hash:"#machines"},
  document:{getElementById:element,
    createElement:tag=>({tag,append(...children){this.children=children;}}),
    querySelectorAll:()=>['image-inspect','image-citrix','image-linux'].map(element)},
  fetch:(...args)=>{calls++;return network(...args);}
});
vm.runInContext(fs.readFileSync(path.join(root,'web/fleet.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'web/images.js'),'utf8'),context);
const app = fs.readFileSync(path.join(root,'web/app.js'),'utf8');
vm.runInContext(app.slice(0,app.indexOf("$('login-form').addEventListener")),context);
vm.runInContext(`renderFleet=f=>{fleetState=f;}; renderUsers=()=>{};
  renderUpdate=()=>{};renderAudit=()=>{};route=()=>{};`,context);
const run = code=>vm.runInContext(code,context);
const state = {csrf:'test',version:'0.2.0',repository:'repo',user:{username:'operator',role:'operator'},
  update:{state:'idle'},events:[]};
const fleet = {devices:[],groups:[]};
const response = body=>({ok:true,status:200,json:async()=>body});
async function main(){
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  network=async url=>{await gate;return response(url==='/api/state'?state:fleet);};
  const first=run('refresh()'), second=run('refresh()');
  assert.equal(first,second,'concurrent refreshes share one request cycle');
  assert.equal(calls,2,'a second refresh must not issue duplicate requests');
  assert.equal(element('refresh-devices').disabled,true);
  assert.equal(element('fleet-monitor')['aria-busy'],'true');
  release();await first;
  assert.equal(element('fleet-monitor').dataset.state,'ready');
  assert.match(element('fleet-monitor-title').textContent,/Aguardando o primeiro agente/);
  assert.equal(element('refresh-devices').disabled,false);
  const last=element('fleet-monitor-last').textContent;
  network=async()=>{throw new Error('Servidor indisponível');};
  await run('refresh()');
  assert.equal(element('fleet-monitor').dataset.state,'error');
  assert.match(element('fleet-monitor-detail').textContent,/dados anteriores podem estar desatualizados/);
  assert.equal(element('fleet-monitor-last').textContent,last,'failure must preserve last success');
  assert.equal(element('refresh-devices').disabled,false,'retry remains available');
  fleet.devices=[{online:true,approved:false}];
  network=async url=>response(url==='/api/state'?state:fleet);
  await run('refresh()');
  assert.equal(element('fleet-monitor').dataset.state,'ready');
  assert.match(element('fleet-monitor-counts').textContent,/1 cadastradas · 1 online · 1 pendentes/);
  run("renderImages({state:'updating',queued:true,worker_ready:true,step:2,versions:{chromium:'123'},log:'<literal>'})");
  assert.equal(element('image-inspect').disabled,true);
  assert.equal(element('image-job-progress').value,2);
  assert.equal(element('image-job-log').textContent,'<literal>');
  run("renderImages({state:'done',queued:false,worker_ready:true,step:5,versions:{chromium:'124'},rollback_available:true})");
  assert.equal(element('image-inspect').disabled,false);
  assert.equal(element('image-rollback').disabled,false);
  run("renderImages({state:'idle',worker_ready:false})");
  assert.equal(element('image-inspect').disabled,true);
  let powerRule;
  vm.runInNewContext(fs.readFileSync(path.join(root,'client/power.rules'),'utf8'),{polkit:{addRule:rule=>{powerRule=rule;},Result:{YES:'allowed'}}});
  const seat={user:'thinclient',local:true,active:true};
  assert.equal(powerRule({id:'org.freedesktop.login1.power-off'},seat),'allowed');
  assert.equal(powerRule({id:'org.freedesktop.login1.reboot'},seat),'allowed');
  assert.equal(powerRule({id:'org.freedesktop.systemd1.manage-units'},seat),undefined);
  for(const change of [{user:'other'},{local:false},{active:false}]) assert.equal(powerRule({id:'org.freedesktop.login1.reboot'},{...seat,...change}),undefined);
  let networkRule, networkProfile={approved:true,allow_network_settings:true};
  vm.runInNewContext(fs.readFileSync(path.join(root,'client/network.rules'),'utf8'),{polkit:{addRule:rule=>{networkRule=rule;},spawn:()=>JSON.stringify(networkProfile),Result:{YES:'allowed',NO:'denied'}}});
  const nm=id=>({id:'org.freedesktop.NetworkManager.'+id});
  for(const action of ['network-control','wifi.scan','settings.modify.own','settings.modify.system','enable-disable-wifi']) assert.equal(networkRule(nm(action),seat),'allowed');
  assert.equal(networkRule(nm('settings.modify.hostname'),seat),'denied');
  networkProfile.allow_network_settings=false;
  assert.equal(networkRule(nm('network-control'),seat),'denied');
  networkProfile={approved:false,allow_network_settings:true};
  assert.equal(networkRule(nm('settings.modify.system'),seat),'denied');
  networkProfile={approved:true,allow_network_settings:true};
  assert.equal(networkRule(nm('network-control'),{...seat,local:false}),'denied');
  assert.equal(networkRule(nm('network-control'),{...seat,active:false}),'denied');
  assert.equal(networkRule(nm('network-control'),{...seat,user:'other'}),undefined);
  assert.equal(networkRule({id:'org.freedesktop.systemd1.manage-units'},seat),undefined);
  // Force the real API timeout handler without waiting fifteen seconds.
  let timeout;
  context.setTimeout=callback=>{timeout=callback;return 1;};context.clearTimeout=()=>{};
  network=(_,options)=>new Promise((resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(Object.assign(new Error(),{name:'AbortError'})));
  });
  const timed=run("api('/timeout')");timeout();
  await assert.rejects(timed,/15 segundos/);
  context.setTimeout=setTimeout;context.clearTimeout=clearTimeout;
  let reloads=0;
  context.location.reload=()=>reloads++;
  context.document.querySelector=()=>({content:'0.2.0'});
  network=async url=>response(url==='/api/state'?{...state,version:'0.2.3'}:fleet);
  await run('refresh()');
  assert.equal(reloads,1,'A new server version must reload the old interface');
  console.log('UI monitor: concurrent refresh, loading, failure, recovery, timeout and image-job controls passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
