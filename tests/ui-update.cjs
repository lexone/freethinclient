const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const elements=new Map();
const element=id=>{if(!elements.has(id))elements.set(id,{textContent:'',scrollHeight:0,scrollTop:0,clientHeight:0,removeAttribute(name){delete this[name];}});return elements.get(id);};
const context=vm.createContext({document:{getElementById:element},Date});
const source=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');
vm.runInContext(source.slice(0,source.indexOf('function refresh(')),context);
const render=update=>{context.update=update;vm.runInContext('renderUpdate(update)',context);};
render({state:'available',version:'0.2.2',signature_valid:true});
assert.equal(element('apply-update').disabled,false);
for(const state of ['queued','checking','downloading','verifying','extracting','backup','applying','health']){
  render({state,log:['<literal>'],timestamp:1});
  assert.equal(element('apply-update').disabled,true);assert.equal(element('check-update').disabled,true);
  assert.equal(element('update-log').textContent,'<literal>');
}
render({state:'updated',version:'0.2.2'});assert.equal(element('update-progress').value,100);
render({state:'error',message:'Falha de assinatura'});assert.match(element('update-job-title').textContent,/Falha de assinatura/);
assert.equal(element('check-update').disabled,false);
console.log('Update monitor passed: queue, stage progress, literal logs, terminal state and duplicate-action prevention');
