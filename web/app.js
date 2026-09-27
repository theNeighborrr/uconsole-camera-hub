'use strict';
const video=$('video'), boxes=$('boxes'), context=video.getContext('2d',{alpha:false});
let state=null,stateAt=0,frameId=0,frameSource='',frameRevision=-1,frameEpoch='',lastFrame=0;
let frameCount=0,statsAt=performance.now(),inferenceCount=null,pendingControl=false;
let boxFilters=readBoxFilters();
$('showPeople').checked=boxFilters.people;$('showVehicles').checked=boxFilters.vehicles;
function notice(message){$('notice').textContent=message;$('notice').classList.toggle('hidden',!message);}
function fit(){const ratio=video.width/video.height,stage=$('stage');const width=Math.min(stage.clientWidth,stage.clientHeight*ratio);$('picture').style.width=width+'px';$('picture').style.height=width/ratio+'px';}
new ResizeObserver(fit).observe($('stage'));
function draw(){
  const now=performance.now();
  const valid=state&&state.live&&state.detection&&state.epoch===frameEpoch&&state.source===frameSource&&state.revision===frameRevision&&now-stateAt<1500&&now-lastFrame<1600&&state.result_age_ms!==null&&state.result_age_ms+now-stateAt<1600;
  paintBoxes(boxes,valid?filteredObjects(state,boxFilters):[],Number($('threshold').value)/100);
}
function update(next){
  if(state&&(state.epoch!==next.epoch||state.revision!==next.revision)){
    frameId=0;lastFrame=0;context.fillStyle='#05090e';context.fillRect(0,0,video.width,video.height);paintBoxes(boxes,[]);
  }
  if(state&&state.epoch!==next.epoch)inferenceCount=null;
  state=next;stateAt=performance.now();
  $('openPhone').hidden=state.source!=='phone';
  $('droneHelp').hidden=state.source!=='drone';
  const ring=state.ring;
  $('ringLive').hidden=$('ringHelp').hidden=!ring?.selected;
  $('ringLive').textContent=ring?.active?'Stop live view':'Start live view';
  if(ring?.selected){
    const left=ring.remaining_seconds;
    $('ringHelp').textContent=`Ring · Internet required · ${ring.active?`${Math.floor(left/60)}:${String(left%60).padStart(2,'0')} remaining`:`${ring.session_seconds/60}-minute sessions`}. Live viewing can affect Ring motion alerts${state.source==='ring_front'?' and uses the doorbell battery':''}.`;
  }
  $('openPhone').textContent=state.phone_connected?'Open phone camera':'Connect phone';
  if(!pendingControl){$('source').value=state.source;$('detect').checked=state.detection;}
  $('detection').textContent=boxSummary(state,boxFilters,Number($('threshold').value)/100);
  draw();
}
async function poll(){while(true){if(!document.hidden){try{const response=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(4000)});if(!response.ok)throw Error('Hub unavailable');update(await response.json());}catch{state=null;draw();$('connection').textContent='Reconnecting to uConsole…';}}await sleep(450);}}
async function stream(){while(true){if(document.hidden){await sleep(250);continue;}const began=performance.now();try{
  const response=await fetch(`/frame?after=${frameId}`,{cache:'no-store',signal:AbortSignal.timeout(6000)});
  if(!response.ok)throw Error(await response.text());
  const source=response.headers.get('X-Source'),revision=Number(response.headers.get('X-Revision')),epoch=response.headers.get('X-Epoch');
  const bitmap=await createImageBitmap(await response.blob());
  if(document.hidden||(state&&(state.source!==source||state.revision!==revision||state.epoch!==epoch))){bitmap.close();continue;}
  frameId=Number(response.headers.get('X-Frame-Id'));frameSource=source;frameRevision=revision;frameEpoch=epoch;
  if(video.width!==bitmap.width||video.height!==bitmap.height){video.width=boxes.width=bitmap.width;video.height=boxes.height=bitmap.height;fit();}
  context.drawImage(bitmap,0,0);bitmap.close();lastFrame=performance.now();frameCount++;
  $('connection').textContent='Live · uConsole';notice('');draw();
}catch(error){lastFrame=0;draw();$('connection').textContent='Waiting for camera…';notice(error.name==='TimeoutError'?'Reconnecting to uConsole…':error.message);await sleep(600);}await sleep(Math.max(0,100-(performance.now()-began)));}}
async function change(settings){pendingControl=true;try{update(await control(settings));}catch(error){notice(error.message);}finally{pendingControl=false;if(state){$('source').value=state.source;$('detect').checked=state.detection;}}}
$('source').onchange=()=>change({source:$('source').value});
$('detect').onchange=()=>change({detection:$('detect').checked});
$('ringLive').onclick=()=>change({ring_action:state?.ring?.active?'stop':'start'});
function changeFilters(){boxFilters={people:$('showPeople').checked,vehicles:$('showVehicles').checked};saveBoxFilters(boxFilters);$('detection').textContent=boxSummary(state,boxFilters,Number($('threshold').value)/100);draw();}
$('showPeople').onchange=changeFilters;$('showVehicles').onchange=changeFilters;
$('openPhone').onclick=async()=>{try{const response=await fetch('/api/phone/open',{method:'POST'});notice(await response.text());}catch{notice('Could not reach the uConsole.');}};
$('threshold').oninput=()=>{$('thresholdValue').value=$('threshold').value+'%';$('detection').textContent=boxSummary(state,boxFilters,Number($('threshold').value)/100);draw();};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('stage').requestFullscreen();}catch{}};
document.addEventListener('visibilitychange',()=>{lastFrame=0;draw();if(!document.hidden)frameId=0;});
setInterval(()=>{draw();const now=performance.now(),seconds=(now-statsAt)/1000;if(seconds>=2){const boxesRate=state&&inferenceCount!==null?Math.max(0,(state.inference_count-inferenceCount)/seconds):0;$('performance').textContent=`Video ${(frameCount/seconds).toFixed(1)} fps · Boxes ${boxesRate.toFixed(1)}/s`;inferenceCount=state?.inference_count??null;frameCount=0;statsAt=now;}if(lastFrame&&now-lastFrame>1600)$('connection').textContent='Waiting for camera…';},250);
async function start(){
  const query=new URLSearchParams(location.search);
  if(query.get('source')==='drone'){
    query.delete('source');history.replaceState(null,'',location.pathname+(query.size?'?'+query.toString():'')+location.hash);
    await change({source:'drone'});
  }
  poll();stream();
}
start();
