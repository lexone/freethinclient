const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
function element(tag='div') {
  return {tag,textContent:'',value:'',children:[],listeners:{},dataset:{},
    append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},
    setAttribute(key,value){this[key]=value;},
    addEventListener(name,handler){this.listeners[name]=handler;},contains(){return false;}};
}
const map=new Map(),get=id=>{if(!map.has(id))map.set(id,element());return map.get(id);};
const keys=[...html.matchAll(/data-page="([^"]+)"/g)].map(match=>match[1]);
const panels=keys.map(key=>({...element(),dataset:{page:key}}));
const tabs=[...html.matchAll(/role="tab"[^>]*href="#([^"]+)"/g)].map(match=>({...element('a'),hash:'#'+match[1]}));
const opened=[];
const context=vm.createContext({Date,JSON,console,addEventListener(){},location:{hash:'#machines'},
  document:{createElement:element,querySelectorAll:selector=>selector==='[data-page]'?panels:tabs},$:get,
  window:{openRemoteConsole:device=>opened.push(device.id)},notify(){throw Error('Console handler unavailable');}});
vm.runInContext('let authenticated=true,remoteAdmin=true;',context);
vm.runInContext(fs.readFileSync(path.join(root,'web/fleet.js'),'utf8'),context);
for(const key of keys) {
  context.location.hash='#'+key;vm.runInContext('route()',context);
  assert.equal(panels.find(panel=>panel.dataset.page===key).hidden,false,'Menu must open '+key);
  assert.equal(panels.filter(panel=>!panel.hidden).length,1);
  assert.equal(tabs.find(tab=>tab.hash==='#'+key)['aria-selected'],'true');
}
const device={id:'test-pc',name:'teste',mac:'02:00:00:00:00:01',approved:true,online:true};
context.device=device;
const render=()=>{vm.runInContext('fleetState={groups:[],devices:[device]};renderDevices(true)',context);};
function buttons(node){return [...(node.tag==='button'?[node]:[]),...node.children.flatMap(buttons)];}
render();let button=buttons(get('device-list')).find(button=>button.textContent==='Console remoto');
assert(button,'An admin must see Console remoto on an approved online device');button.listeners.click();
assert.deepEqual(opened,['test-pc']);
for(const change of [{online:false},{approved:false}]) {
  Object.assign(device,{online:true,approved:true},change);render();
  assert(!buttons(get('device-list')).some(button=>button.textContent==='Console remoto'));
}
Object.assign(device,{online:true,approved:true});vm.runInContext('remoteAdmin=false',context);render();
assert(!buttons(get('device-list')).some(button=>button.textContent==='Console remoto'));
assert.match(html,/<input[^>]*id="remember-login"[^>]*name="remember"[^>]*type="checkbox"/);
assert.match(html,/Manter conectado por 30 dias/);
assert.match(html,/<dialog[^>]*id="remote-dialog"/);
console.log('Navigation passed: every menu route, visible console button and click, role/device restrictions and remembered-login control');
