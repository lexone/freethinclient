const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),elements=new Map();
function element(id){
  if(!elements.has(id))elements.set(id,{textContent:'',value:'',hidden:false,listeners:{},
    addEventListener(name,fn){this.listeners[name]=fn;},
    replaceChildren(...children){this.children=children;if(id==='network-group')this.value=children[0]?.value || '';},
    reset(){},elements:{},append(...children){this.children=children;}});
  return elements.get(id);
}
const form=element('network-settings');
for(const name of ['dns_override','allow_network_settings','dns_servers','dns_search'])form.elements[name]={checked:false,value:''};
let saved;
const context=vm.createContext({console,structuredClone,Date,Array,JSON,addEventListener(){},
  $:element,confirm:()=>true,notify(){},
  node:(tag,kind,text)=>({tag,kind,text,append(...children){this.children=children;}}),
  api:async(_,data)=>{saved=data;},refresh:async()=>{}});
vm.runInContext(`let fleetState={groups:[],devices:[]};`,context);
vm.runInContext(fs.readFileSync(path.join(root,'web/network.js'),'utf8'),context);
const run=source=>vm.runInContext(source,context);
async function main(){
  run(`initializeNetworkUI();fleetState.groups=[{id:'lab',name:'Lab',revision:1,dns_servers:['10.0.0.10']}];renderNetworkGroups(fleetState.groups);`);
  assert.equal(form.elements.dns_servers.value,'10.0.0.10');
  form.elements.dns_servers.value='10.0.0.11';form.elements.dns_override.checked=true;form.elements.allow_network_settings.checked=true;
  form.listeners.input();
  run(`fleetState.groups[0].revision=2;fleetState.groups[0].dns_servers=['10.0.0.12'];renderNetworkGroups(fleetState.groups);`);
  assert.equal(form.elements.dns_servers.value,'10.0.0.11','polling must preserve unsaved DNS edits');
  await form.listeners.submit({preventDefault(){},target:form});
  assert.equal(saved.id,'lab');assert.equal(saved.dns_servers,'10.0.0.11');
  assert.equal(saved.dns_override,true);assert.equal(saved.allow_network_settings,true);
  run(`renderNetworkGroups([])`);assert.equal(form.hidden,true);
  console.log('Network editor: group selection, DNS values, unsaved edit preservation and typed save passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
