"use strict";
const $=id=>document.getElementById(id), page=document.body.dataset.page;
const escapeHtml=value=>String(value??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=value=>value==null?"—":Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
const time=value=>value?new Date(value*1000).toLocaleTimeString():"—";
const stamp=value=>value?new Date(value*1000).toLocaleString():"—";
function set(id,html){if($(id))$(id).innerHTML=html}
function put(id,value){if($(id))$(id).textContent=value}
function pairs(entries){return entries.map(([k,v])=>'<div class="pair"><span>'+escapeHtml(k)+'</span><strong>'+escapeHtml(v)+'</strong></div>').join("")}
function table(headers,rows){return '<div class="scroll"><table><thead><tr>'+headers.map(x=>'<th>'+x+'</th>').join("")+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>'}
async function api(path,body){const res=await fetch("/api/"+path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});const obj=await res.json();if(!res.ok)throw Error(obj.error||res.statusText);return obj.data}
function action(id,fn){if($(id))$(id).onclick=async()=>{try{put("notice","");await fn()}catch(e){put("notice",e.message)}}}
let paused=false, latest=[], historyRows=[], config={}, previous=null, runMode="", shownThreshold=false, busy=false, currentId="",lastEvent=0, first=true;
const series=[];
function badge(label){return '<span class="badge '+(label==="CRITICAL"?"CRITICAL":"NORMAL")+'">'+escapeHtml(label)+'</span>'}
function inspect(m,out=false){
 const details=out?[["Message",m.text],["ID",m.id],["Status",m.status],["Queue wait (ms)",fmt(m.wait_ms)],["Acknowledgement RTT (ms)",fmt(m.rtt_ms)]]:
 [["Message",m.text],["ID",m.id],["Priority",m.label],["P(critical) / model score",fmt(m.score)],["From / to",m.sender+" → "+(m.receiver||m.destination||"—")],["Payload",new TextEncoder().encode(m.text).length+" bytes"],["Classification (ms)",fmt(m.classification_ms)],["Queue wait (ms)",fmt(m.wait_ms)],["Delivery latency (ms)",fmt(m.latency_ms)],["Timing method",m.measurement],["Sent",new Date(m.sent*1000).toISOString()],["Received",new Date(m.received*1000).toISOString()],["Delivery status",m.status]];
 set("fields",pairs(details));set("correct",out?"":'<p><button id="fix">Record correction to '+(m.label==="CRITICAL"?"NORMAL":"CRITICAL")+'</button></p>');
 action("fix",async()=>put("correct",await api("control/feedback",{id:m.id,label:m.label==="CRITICAL"?"NORMAL":"CRITICAL"})));
 $("detail").showModal()
}
action("close",()=>$("detail").close());
function stream(){
 if(!$("stream"))return;
 const q=($("query")?.value||"").toLowerCase(), sender=($("sender")?.value||"").toLowerCase(), label=$("label")?.value;
 const rows=latest.filter(m=>(!label||m.label===label)&&m.sender.toLowerCase().includes(sender)&&(m.text+" "+m.id).toLowerCase().includes(q)).slice(0,page?500:5);
 set("stream",rows.length?table(["Message ID","Message","Priority","Route","Delivery (ms)","Received"],rows.map(m=>['<button class="link" data-id="'+escapeHtml(m.id)+'">'+escapeHtml(m.id.slice(0,8))+'</button>',escapeHtml(m.text),badge(m.label),escapeHtml(m.sender+" → "+(m.receiver||"receiver")),fmt(m.latency_ms),time(m.received)])):"<p>No matching deliveries.</p>");
 $("stream").querySelectorAll("button").forEach(b=>b.onclick=()=>inspect(rows.find(m=>m.id===b.dataset.id)))
}
["query","sender","label"].forEach(id=>{if($(id))$(id).oninput=stream});
action("pause",()=>{paused=!paused;put("pause",paused?"Resume live feed":"Pause live feed");if(!paused)refresh()});
action("clear",async()=>{if(confirm("Clear received loopback demo messages?")){await api("control/clear",{});paused=false;put("pause","Pause live feed");await refresh()}});
function evalPanel(report){if(!$("evaluation"))return;
 const m=report.test, pct=x=>fmt(x*100)+"%";
 set("evaluation",pairs([["Selected classifier",report.selected],["Synthetic corpus · train / validation / test",report.split_sizes.join(" / ")],["Trained",stamp(report.trained_at)],["Evaluation threshold",report.threshold],["Accuracy",pct(m.accuracy)],["Critical precision / recall / F1",[m.precision,m.recall,m.f1].map(pct).join(" / ")]])+table(["Actual ↓ / predicted →","Critical","Normal"],m.confusion_matrix.map((row,i)=>[i?"Normal":"Critical",...row]))+"<small>Held-out synthetic scenarios. Real-world performance is unknown.</small>")
}
function comparison(data){if(!$("comparison"))return;
 if(!data.fcfs){put("comparison","No comparison run yet.");return}
 const rows=Object.keys(data.fcfs).map(key=>[key,fmt(data.fcfs[key]),fmt(data.priority[key])]);
 const key="CRITICAL mean delay (ms)", a=data.fcfs[key],b=data.priority[key];
 set("comparison",table(["Simulated metric","FCFS","Priority"],rows)+(a==null?"<p>No critical predictions in this workload.</p>":"<p>Mean critical delay "+(a>b?"fell by "+fmt(a-b)+" ms":a===b?"was equal under both policies":"increased by "+fmt(b-a)+" ms")+".</p>"+["fcfs","priority"].map(k=>'<small>'+k+' · '+fmt(data[k][key])+' ms</small><div class="meter" style="width:'+100*data[k][key]/Math.max(a,b,1)+'%"></div>').join("")))
}
function bars(values,unit){const max=Math.max(1,...values);return '<div class="chart">'+values.map((v,i)=>'<i tabindex="0" title="'+(i+1)+': '+v+' '+unit+'" style="height:'+Math.max(1,v/max*100)+'%"></i>').join("")+'</div>'}
async function refresh(){
 if(busy)return;busy=true;
 try{
 const [s,m,c,rows,events]=await Promise.all([api("health"),api("metrics"),api("console"),$("stream")||page==="analytics"?api("messages?limit=500"):[],(!page||page==="analytics")?api("activity"):[]]);
 config=s.config;runMode=c.demo?"Local demo":"LAN configuration";put("online",s.online?"● Online":"Offline");put("mode",runMode);
 const cq=s.queues.CRITICAL,nq=s.queues.NORMAL,cr=m.classes.CRITICAL,no=m.classes.NORMAL,total=cr.n+no.n;
 const active=c.demo?1:1+Number(Date.now()/1000-(c.last.transmitted||0)<60);
 set("stats",[["Received messages",total],["Critical",cr.n],["Normal",no.n],["Mean delivery (ms)",fmt(m.avg_network)],["Active nodes · 60 s",active],["Waiting messages",cq.waiting+nq.waiting]].map(([k,v])=>'<div class="stat"><small>'+k+'</small><b>'+v+'</b></div>').join(""));
 set("systems",pairs([["Sender middleware",s.sender?"Running":"Stopped"],["Receiver middleware",s.receiver?"Listening":"Stopped"],["ML classifier",s.model?"Loaded":"Unavailable"],["Priority scheduler",s.sender?"Running":"Stopped"],["TCP peer",c.last.transmitted?"Last ACK "+time(c.last.transmitted):"Awaiting acknowledgement"],["SQLite database",s.database]]));
 set("queues",[["CRITICAL",cq],["NORMAL",nq]].map(([l,q])=>'<div class="pair">'+badge(l)+'<b>'+q.waiting+' waiting</b></div><small>'+escapeHtml(q.previews.join(" · ")||"Queue empty")+'</small>').join(""));
 if($("pipeline")){const e=events[0], stage=({"classified":1,"queued":2,"frame transmitted":3,"received":4,"transmitted":4,"disconnected":4})[e?.event];if(e?.seq!==lastEvent){set("pipeline",["Intercept","Classify","Prioritize","Deliver","Display"].map((x,i)=>'<span class="'+(i===stage?"current":"")+'">'+x+'</span>').join(""));put("event",e?time(e.at)+" · "+e.event:"Waiting for activity");lastEvent=e?.seq}}
 if(!paused){if(page==="monitor"&&!first){const alert=rows.find(m=>m.label==="CRITICAL"&&m.received>(previous||0));if(alert)put("alert","Critical delivery · "+alert.text+" · "+fmt(alert.latency_ms)+" ms")}latest=rows;previous=rows[0]?.received||0;first=false;stream()}
 if($("clear"))$("clear").disabled=!c.demo;
 if($("source")){$("source").value=config.node;$("dest").value=config.peer_host+":"+config.peer_port}
 historyRows=c.history;
 if($("history")){set("history",c.history.length?table(["Message","Priority","Status","ACK RTT (ms)"],c.history.map((r,i)=>['<button class="link" data-index="'+i+'">'+escapeHtml(r.text||r.id)+'</button>',badge(r.label),escapeHtml(r.status),fmt(r.rtt_ms)])):"<p>No submissions yet.</p>");$("history").querySelectorAll("button").forEach(b=>b.onclick=()=>inspect(historyRows[b.dataset.index],true));if(currentId){const r=c.history.find(r=>r.id===currentId);if(r)put("deliveryStatus",r.status)}}
 put("runstatus",c.run);comparison(c.comparison);
 if(page==="analytics"){set("distribution",total?[["CRITICAL",cr.n],["NORMAL",no.n]].map(([l,n])=>badge(l)+" "+n+" messages ("+fmt(n/total*100)+'% )<div class="meter" style="width:'+n/total*100+'%"></div>').join(""):"No messages received yet.");set("throughput",bars(m.minutes,"messages per minute")+"<small>Oldest minute on the left · "+m.minutes.reduce((a,b)=>a+b,0)+" messages in this window.</small>");
 set("latency",table(["Metric (ms)","Critical","Normal"],[["Mean delivery",fmt(cr.avg_network),fmt(no.avg_network)],["p95 delivery",fmt(cr.p95_network),fmt(no.p95_network)],["Mean queue wait",fmt(cr.avg_wait),fmt(no.avg_wait)],["Maximum wait",fmt(cr.max_wait),fmt(no.max_wait)]]));series.push(cq.waiting+nq.waiting);if(series.length>60)series.shift();set("timeline",bars(series,"queued")+"<small>Queue depth sampled while this page is open. Recent classifications below.</small>"+table(["Received","Priority","Classifier time (ms)"],rows.slice(0,6).map(r=>[time(r.received),badge(r.label),fmt(r.classification_ms)])))}
 if($("evaluation")&&!shownThreshold){const [report,settings]=await Promise.all([api("model/status"),api("settings")]);evalPanel(report);if($("threshold"))$("threshold").value=settings.threshold;shownThreshold=true}
 if($("cfgName")&&!$("cfgName").dataset.ready){for(const [id,k] of [["cfgName","node"],["cfgBind","listen_host"],["cfgPeer","peer_host"],["cfgPort","peer_port"]])$(id).value=config[k];$("cfgName").dataset.ready="1"}
 if($("nodeinfo"))set("nodeinfo",pairs([["Local node / role",config.node+" · sender and receiver"],["Listening",config.listen_host+":"+config.tcp_port],["Configured receiver",config.peer_host+":"+config.peer_port],["Acknowledged / received",c.sent+" / "+total],["Last acknowledgement",stamp(c.last.transmitted)],["Last received",stamp(c.last.received)],["Failed attempts",c.errors],["One-way timing",c.demo?"Monotonic clock":config.clocks_synced?"UTC estimate · configured as synchronized":"Unavailable across unsynchronized machines"]]));
 }catch(e){put("online","Disconnected");put("notice",e.message)}finally{busy=false}
}
if($("compose"))$("compose").onsubmit=async e=>{e.preventDefault();try{const m=await api("messages/send",{text:$("message").value,domain:$("domain").value});currentId=m.id;set("receipt",badge(m.label)+" queue · "+fmt(m.classification_ms)+" ms classification · "+escapeHtml(m.score_kind)+" score for critical "+fmt(m.score)+"<br>"+escapeHtml(m.id)+' · <strong id="deliveryStatus">Queued</strong>');await refresh()}catch(e){put("receipt",e.message)}};
document.querySelectorAll(".sample").forEach(btn=>btn.onclick=()=>{$("message").value=btn.textContent;$("domain").value=btn.dataset.domain});
if($("critical"))$("critical").oninput=()=>put("normalpct",100-Number($("critical").value));
function opts(){return Object.fromEntries([...["count","critical","interval","service"].map(k=>[k,Number($(k).value)]),["domain",$("domain").value],["mode",$("policy").value]])}
action("start",async()=>{await api("control/lab/run",opts());await refresh()});action("stop",async()=>{await api("control/lab/stop",{});await refresh()});action("compare",async()=>comparison(await api("control/lab/compare",opts())));
action("probe",async()=>put("probeResult",await api("control/peer",{})));
action("apply",async()=>{const r=await api("control/model/threshold",{threshold:Number($("threshold").value)});put("modelresult","Applied "+r.threshold+" · validation precision "+fmt(r.validation.precision)+" · recall "+fmt(r.validation.recall)+" · F1 "+fmt(r.validation.f1))});
action("train",async()=>{put("modelresult","Training candidate classifiers…");const r=await api("control/model/retrain",{});shownThreshold=false;put("modelresult","Model reloaded. Eligible feedback records: "+r.feedback_included);await refresh()});
refresh();setInterval(refresh,900);
if(!page||page==="monitor"||page==="traffic-lab"){
 const source=new EventSource("/api/events");
 let displayed=0;
 const steps=["Intercept","Classify","Prioritize","Deliver","Display"];
 source.onmessage=e=>{
  const batch=JSON.parse(e.data);
  if(!page){
   const stages={intercepted:0,classified:1,queued:2,"frame transmitted":3,received:4};
   const events=batch.filter(x=>x.event in stages);
   const id=events.find(x=>x.event==="received")?.detail.split(" ").pop();
   const chosen=id?events.filter(x=>x.detail.includes(id)):events.slice(-5);
   const version=++displayed;
   chosen.forEach((entry,i)=>setTimeout(()=>{
     if(version!==displayed)return;
     set("pipeline",steps.map((x,j)=>'<span class="'+(j===stages[entry.event]?"current":"")+'">'+x+'</span>').join(""));
     put("event","Recorded event · "+entry.event+" · "+entry.detail);
   },i*150))
  }
  refresh()
 };
 window.addEventListener("pagehide",()=>source.close())
}
