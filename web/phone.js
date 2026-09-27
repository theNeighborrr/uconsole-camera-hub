'use strict';
const preview=$('preview'), overlay=$('overlay'), sample=document.createElement('canvas');
const context=sample.getContext('2d',{alpha:false});
let media=null,generation=0,owner=null,wakeLock=null,lastState=0,shared=null,controller=null;
let boxFilters=readBoxFilters();
$('showPeople').checked=boxFilters.people;$('showVehicles').checked=boxFilters.vehicles;
function status(message){$('status').textContent=message;}
function draw(){const valid=media&&shared?.source==='phone'&&shared.detection&&shared.live&&performance.now()-lastState<1500&&shared.result_age_ms!==null&&shared.result_age_ms+performance.now()-lastState<1600;paintBoxes(overlay,valid?filteredObjects(shared,boxFilters):[]);}
async function stop(message='Camera is off. Tap Start camera to send again.'){
  generation++;controller?.abort();const oldOwner=owner;owner=null;
  media?.getTracks().forEach(track=>track.stop());media=null;preview.srcObject=null;paintBoxes(overlay,[]);
  wakeLock?.release().catch(()=>{});wakeLock=null;$('start').disabled=false;$('stop').disabled=true;status(message);
  if(oldOwner)fetch('/phone/stop',{method:'POST',headers:{'X-Publisher-Id':oldOwner},keepalive:true}).catch(()=>{});
}
async function start(){
  await stop();const ownGeneration=++generation;$('start').disabled=true;status('Opening camera…');
  try{
    if(!window.isSecureContext||!navigator.mediaDevices)throw Error('Open this phone page through its uConsole connection at http://127.0.0.1:8765/phone.html.');
    const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{facingMode:{ideal:$('facing').value},width:{ideal:640},height:{ideal:480},frameRate:{ideal:10,max:15}}});
    if(ownGeneration!==generation){stream.getTracks().forEach(track=>track.stop());return;}
    media=stream;preview.srcObject=stream;await preview.play();
    if(ownGeneration!==generation)return;
    await control({source:'phone'});
    if(ownGeneration!==generation)return;
    owner=crypto.randomUUID();$('stop').disabled=false;
    try{wakeLock=await navigator.wakeLock?.request('screen');}catch{}
    upload(ownGeneration,owner);
  }catch(error){if(ownGeneration===generation)await stop(error.name==='NotAllowedError'?'Allow camera access, then tap Start camera.':error.message);}
}
async function upload(ownGeneration,publisher){
  while(media&&generation===ownGeneration){const began=performance.now();try{
    const width=preview.videoWidth,height=preview.videoHeight;if(!width){await sleep(100);continue;}
    sample.width=Math.min(640,width);sample.height=Math.round(height*sample.width/width);
    if(overlay.width!==width||overlay.height!==height){overlay.width=width;overlay.height=height;}
    context.drawImage(preview,0,0,sample.width,sample.height);
    const jpeg=await new Promise(resolve=>sample.toBlob(resolve,'image/jpeg',.72));
    if(generation!==ownGeneration||!jpeg)return;
    controller=new AbortController();const timeout=setTimeout(()=>controller?.abort(),5000);
    let response;try{response=await fetch('/phone/frame',{method:'POST',headers:{'Content-Type':'image/jpeg','X-Publisher-Id':publisher},body:jpeg,signal:controller.signal});}finally{clearTimeout(timeout);}
    if(!response.ok)throw Error(await response.text());
    if(generation===ownGeneration)status(shared?.source==='phone'?'Sending to uConsole · Keep this page open':'Camera ready · Another source is selected on the uConsole');
  }catch(error){if(generation===ownGeneration){status('Connection interrupted. Retrying… '+error.message);await sleep(700);}}
    await sleep(Math.max(0,100-(performance.now()-began)));
  }
}
async function poll(){while(true){if(media&&!document.hidden){try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error();shared=await response.json();lastState=performance.now();$('boxesToggle').checked=shared.detection;$('detection').textContent=boxSummary(shared,boxFilters);draw();}catch{shared=null;draw();}}await sleep(450);}}
$('start').onclick=start;$('stop').onclick=()=>stop();$('facing').onchange=()=>{if(media)start();};
$('boxesToggle').onchange=()=>control({detection:$('boxesToggle').checked}).catch(error=>status(error.message));
function changeFilters(){boxFilters={people:$('showPeople').checked,vehicles:$('showVehicles').checked};saveBoxFilters(boxFilters);$('detection').textContent=boxSummary(shared,boxFilters);draw();}
$('showPeople').onchange=changeFilters;$('showVehicles').onchange=changeFilters;
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop('Camera paused because this page was hidden. Tap Start camera to resume.');});
window.addEventListener('pagehide',()=>stop());setInterval(draw,250);poll();
