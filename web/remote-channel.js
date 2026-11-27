// WebSocket-compatible channel for noVNC, carried by authenticated HTTPS.
// Stop-and-wait sequence numbers make retries safe for both screen and input.
export default class RemoteChannel {
  constructor(id, api, status) {
    this.id=id; this.api=api; this.status=status; this.readyState=0;
    this.binaryType='arraybuffer'; this.protocol=''; this.bufferedAmount=0;
    this.onopen=null; this.onclose=null; this.onerror=null; this.onmessage=null;
    this.queue=[]; this.sequence=1;
    setTimeout(()=>this.loop(),0);
  }
  send(bytes) {
    const copy=new Uint8Array(bytes).slice();
    this.bufferedAmount+=copy.length;
    if(this.bufferedAmount>2*1024*1024) {this.fail('Conexão lenta: fila de entrada cheia.');return;}
    this.queue.push(copy);
  }
  close() {
    if(this.readyState===3)return;
    this.readyState=3;this.queue=[];this.bufferedAmount=0;
    this.api('/api/remote/stop',{id:this.id}).catch(()=>{});
    this.onclose?.({code:1000,reason:'Console encerrado',wasClean:true});
  }
  fail(message) {this.status(message);this.onerror?.(new Error(message));this.close();}
  async loop() {
    while(this.readyState!==3) {
      const chunks=[];let length=0;
      while(this.queue.length && length+this.queue[0].length<=256*1024) {
        const next=this.queue.shift();chunks.push(next);length+=next.length;
      }
      const outgoing=new Uint8Array(length);let offset=0;
      for(const chunk of chunks){outgoing.set(chunk,offset);offset+=chunk.length;}
      this.bufferedAmount-=length;
      let text='';for(let i=0;i<length;i+=8192)text+=String.fromCharCode(...outgoing.subarray(i,i+8192));
      const payload={id:this.id,seq:this.sequence,data:btoa(text)};
      let reply;
      for(let attempt=0;attempt<3 && this.readyState!==3;attempt++) {
        try {reply=await this.api('/api/remote/poll',payload);break;}
        catch(error){if(attempt===2){this.fail(error.message);return;}await new Promise(r=>setTimeout(r,300));}
      }
      if(this.readyState===3)return;
      this.sequence++;
      if(reply.closed || reply.state==='error'){this.fail(reply.message||'Console encerrado.');return;}
      this.status(reply.message||'Conectando');
      if(reply.state==='connected' && this.readyState===0){this.readyState=1;this.onopen?.();}
      if(reply.data){const binary=atob(reply.data),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));this.onmessage?.({data:bytes.buffer});}
      await new Promise(r=>setTimeout(r,reply.data?0:60));
    }
  }
}
