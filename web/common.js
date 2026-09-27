'use strict';
const $ = id => document.getElementById(id);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const filterButton=$('toggleFilters'),filterPanel=$('filterPanel');
if(filterButton&&filterPanel){
  function setFiltersOpen(open){filterPanel.hidden=!open;filterButton.setAttribute('aria-expanded',String(open));}
  filterButton.onclick=()=>setFiltersOpen(filterPanel.hidden);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!filterPanel.hidden){const returnFocus=filterPanel.contains(document.activeElement);setFiltersOpen(false);if(returnFocus)filterButton.focus();}});
}
async function control(settings) {
  const response=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
  if(!response.ok)throw new Error(await response.text());
  return response.json();
}
const FILTER_KEY='uconsole.camera.box-filters.v1';
function readBoxFilters(){
  try{const saved=JSON.parse(localStorage.getItem(FILTER_KEY));return {people:saved?.people!==false,vehicles:saved?.vehicles!==false};}
  catch{return {people:true,vehicles:true};}
}
function saveBoxFilters(filters){try{localStorage.setItem(FILTER_KEY,JSON.stringify(filters));}catch{}}
function filteredObjects(state,filters){
  return [...(filters.people?(state?.people||[]).map(item=>({...item,kind:'person'})):[]),
    ...(filters.vehicles?(state?.vehicles||[]).map(item=>({...item,kind:'vehicle'})):[])];
}
function boxSummary(state,filters,threshold=.5){
  if(!state?.detection)return 'Detection off';
  if(!state.live)return 'Waiting for camera…';
  if(!filters.people&&!filters.vehicles)return 'Boxes hidden on this screen';
  if(!['Detection ready','Person detection ready'].includes(state.detector_status))return state.detector_status||'Detection unavailable';
  const objects=filteredObjects(state,filters).filter(item=>item.score>=threshold);
  const people=objects.filter(item=>item.kind==='person').length,vehicles=objects.length-people;
  const counts=[];if(people)counts.push(`${people} ${people===1?'person':'people'}`);if(vehicles)counts.push(`${vehicles} ${vehicles===1?'vehicle':'vehicles'}`);
  return counts.length?counts.join(' · '):'No selected objects detected';
}
function paintBoxes(canvas, objects, threshold=.5) {
  const context=canvas.getContext('2d');context.clearRect(0,0,canvas.width,canvas.height);
  const font=Math.max(14,Math.round(canvas.width/38));
  context.font=`bold ${font}px system-ui`;context.lineWidth=Math.max(2,canvas.width/260);
  for(const item of objects.filter(item=>item.score>=threshold)) {
    const [left,top,width,height]=item.bbox;
    const x=left*canvas.width,y=top*canvas.height,w=width*canvas.width,h=height*canvas.height;
    const vehicle=item.kind==='vehicle',color=vehicle?'#ffd54a':'#65ff92';
    const name=vehicle?(['car','motorcycle','bus','truck'].includes(item.label)?item.label:'vehicle'):'person';
    const label=`${name} ${Math.round(item.score*100)}%`,labelY=Math.max(0,y-font-7);
    context.strokeStyle=color;context.strokeRect(x,y,w,h);
    context.fillStyle=color;context.fillRect(x,labelY,context.measureText(label).width+10,font+7);
    context.fillStyle='#082416';context.fillText(label,x+5,labelY+font);
  }
}
