/* FabWatch engineering workbench. No third-party runtime or remote chart assets. */
const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = (value, digits=1) => value == null ? '—' : (value*100).toFixed(digits)+'%';
const fmt = (value, digits=2) => value == null ? '—' : Number(value).toLocaleString('en-US',{maximumFractionDigits:digits});
const colors = ['#426ee6','#18999b','#cd7847'];
const state = {view:'workbench', catalog:[], suggested:[], traces:[], rows:[], cases:[], overview:null,
  analysis:null, selected:null, entity:null, pins:new Map(), filter:'all', page:0, sort:'event_time', desc:true,
  allSignals:false, playing:false, busy:false, timer:null, refreshId:0, dirty:false, lastSync:0, sessions:[]};
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4200)}
function fail(error){$('#error').hidden=false;$('#error').textContent=error.message;$('#connection-dot').classList.add('offline');$('#connection').textContent='Connection interrupted';stopReplay()}
async function api(path,options){const response=await fetch('/api/'+path,options);if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{detail=response.statusText}throw Error(typeof detail==='string'?detail:'Request rejected. Check the data contract.')}return response.json()}
const post = path => api(path,{method:'POST'});
const badge = (value,label=value) => `<span class="badge ${esc(value)}">${esc(label)}</span>`;
const outcome = value => value==null?badge('pending'):value?badge('fail','failed'):badge('pass');
function switchView(view){state.view=view;document.querySelectorAll('.view').forEach(node=>node.hidden=node.id!==view);document.querySelectorAll('nav button').forEach(button=>button.classList.toggle('active',button.dataset.view===view));const full=['quality','model'].includes(view);$('#shell').classList.toggle('full-width',full);$('#inspector').hidden=full;window.scrollTo({top:0,behavior:'instant'});if(view==='quality')renderQuality();if(view==='model')loadModel().catch(fail)}
document.querySelectorAll('nav button').forEach(button=>button.onclick=()=>switchView(button.dataset.view));
$('#model-state').onclick=()=>switchView('model');
$('#help-button').onclick=()=>$('#help-dialog').showModal();$('#close-help').onclick=()=>$('#help-dialog').close();$('#close-compare').onclick=()=>$('#compare-dialog').close();

function renderSignalList(){
  const search=$('#signal-search').value.toLowerCase();
  const candidates=state.catalog.filter(signal=>(state.allSignals||state.suggested.includes(signal.sensor)||state.traces.includes(signal.sensor))&&signal.sensor.includes(search));
  $('#signal-list').innerHTML=candidates.slice(0,100).map(signal=>{const index=state.traces.indexOf(signal.sensor);return `<label class="signal-option ${index>=0?'selected':''}"><input type="checkbox" data-signal="${signal.sensor}" ${index>=0?'checked':''} aria-label="Plot ${signal.sensor}"><span><strong>${signal.sensor}</strong><small>${pct(1-signal.training_missing_fraction,0)} train coverage</small></span>${index>=0?`<i class="signal-color" style="background:${colors[index]}"></i>`:''}</label>`}).join('')||'<div class="empty">No matching signals.</div>';
}
$('#signal-search').oninput=renderSignalList;
$('#suggested-signals').onclick=()=>{state.allSignals=false;$('#suggested-signals').classList.add('active');$('#all-signals').classList.remove('active');renderSignalList()};
$('#all-signals').onclick=()=>{state.allSignals=true;$('#all-signals').classList.add('active');$('#suggested-signals').classList.remove('active');renderSignalList()};
$('#signal-list').onchange=async event=>{const sensor=event.target.dataset.signal;if(!sensor)return;if(event.target.checked){if(state.traces.length>=3){event.target.checked=false;toast('Keep up to three traces. Remove a selected signal first.');return}state.traces.push(sensor)}else{if(state.traces.length===1){event.target.checked=true;toast('Keep one signal selected.');return}state.traces=state.traces.filter(value=>value!==sensor)}if(state.traces.length>1)$('#plot-scale').value='standard';renderSignalList();await refresh().catch(fail)};
$('#reset-view').onclick=async()=>{state.traces=state.suggested.slice(0,3);state.filter='all';state.page=0;$('#record-search').value='';$('#plot-scale').value='standard';$('#window-size').value='all';$('#follow-latest').checked=true;document.querySelectorAll('[data-filter]').forEach(button=>button.classList.toggle('active',button.dataset.filter==='all'));renderSignalList();await refresh().catch(fail)};

function visibleRows(){
  let rows=state.rows;
  const size=$('#window-size').value;
  const count=size==='all'?rows.length:Math.min(Number(size),rows.length);
  const max=Math.max(0,rows.length-count);
  $('#window-position').max=max;
  let start=Math.min(Number($('#window-position').value),max);
  if($('#follow-latest').checked)start=max;
  $('#window-position').value=start;
  $('#window-position').disabled=max===0;
  $('#window-label').textContent=rows.length?`${start+1}–${start+count} / ${rows.length}`:'No records';
  return rows.slice(start,start+count);
}
function reference(sensor){return state.catalog.find(item=>item.sensor===sensor)}
$('#plot-scale').insertAdjacentHTML('beforeend','<option value="ewma">EWMA / train SD</option>');
function zscore(row,sensor){const value=row.signals[sensor],r=reference(sensor);return value==null?null:(value-r.median)/r.sd}
function titleFor(row){return `${row.entity_id} | ${row.event_time} | risk ${pct(row.risk,2)} | missing ${pct(row.missing_fraction)} | ${row.failed==null?'outcome pending':row.failed?'failed':'passed'}`}
function pathFor(values,xx,yy){let drawing='',connected=false;values.forEach((value,i)=>{if(value==null||!Number.isFinite(value)){connected=false;return}drawing+=(connected?'L':'M')+xx(i).toFixed(2)+','+yy(value).toFixed(2)+' ';connected=true});return drawing}
function renderCharts(){
  const rows=visibleRows();
  $('#signal-count').textContent=`${state.traces.length} signal${state.traces.length===1?'':'s'}`;
  $('#signal-legend').innerHTML=state.traces.map((sensor,i)=>`<span><i style="background:${colors[i]}"></i>${sensor}</span>`).join('');
  if(!rows.length){$('#signal-chart').innerHTML='<div class="empty">Run or step the archive replay to begin analysis.</div>';$('#risk-chart').innerHTML='';$('#heatmap').innerHTML='<div class="empty">The process fingerprint appears as records arrive.</div>';renderLedger();return}
  const raw=$('#plot-scale').value==='native';
  const isEwma=$('#plot-scale').value==='ewma';
  const w=760,h=212,left=34,right=12,top=13,bottom=23;
  const series=state.traces.map(sensor=>rows.map(row=>raw?row.signals[sensor]:isEwma?(row.ewma[sensor]?(row.ewma[sensor].value-(reference(sensor).mean??reference(sensor).median))/reference(sensor).sd:null):zscore(row,sensor)));
  const numbers=series.flat().filter(Number.isFinite);
  const span=Math.min(12,Math.max(3.6,...numbers.map(Math.abs)));
  let min=raw?(numbers.length?Math.min(...numbers):0):-span,max=raw?(numbers.length?Math.max(...numbers):1):span;
  if(max===min){max+=1;min-=1}if(raw){const pad=(max-min)*.12;max+=pad;min-=pad}
  const xx=i=>left+i*(w-left-right)/Math.max(1,rows.length-1);
  const yy=value=>top+(h-top-bottom)*(1-(Math.max(min,Math.min(max,value))-min)/(max-min));
  const selectedIndex=rows.findIndex(row=>row.entity_id===state.selected);
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Process signal overlay"><title>Process signal overlay, click any record column to inspect</title><g aria-hidden="true">`;
  if(!raw&&!isEwma)svg+=`<rect x="${left}" y="${yy(3)}" width="${w-left-right}" height="${yy(-3)-yy(3)}" fill="#f4f7fd"/>`;
  for(let tick=0;tick<=4;tick++){const value=min+(max-min)*tick/4;svg+=`<line x1="${left}" y1="${yy(value)}" x2="${w-right}" y2="${yy(value)}" stroke="#e6ebf4"/><text x="1" y="${yy(value)+3}">${fmt(value,raw?1:0)}</text>`}
  if(!raw&&!isEwma)for(const value of [-3,3])svg+=`<line x1="${left}" y1="${yy(value)}" x2="${w-right}" y2="${yy(value)}" stroke="#b6c6e4" stroke-dasharray="3 4"/>`;
  if(isEwma){const sensor=state.traces[0],r=reference(sensor),mean=r.mean??r.median;for(const key of ['upper','lower']){const bounds=rows.map(row=>row.ewma[sensor]?(row.ewma[sensor][key]-mean)/r.sd:null);svg+=`<path d="${pathFor(bounds,xx,yy)}" fill="none" stroke="#c69d68" stroke-width="1" stroke-dasharray="3 3"/>`}}
  if(!numbers.length)svg+=`<text x="${w/2}" y="${h/2}" text-anchor="middle">No finite measurements for this signal and window</text>`;
  series.forEach((values,i)=>svg+=`<path d="${pathFor(values,xx,yy)}" fill="none" stroke="${colors[i]}" stroke-width="1.35"/>`);
  if(selectedIndex>=0)svg+=`<line x1="${xx(selectedIndex)}" x2="${xx(selectedIndex)}" y1="${top}" y2="${h-bottom}" stroke="#7e98c5" stroke-dasharray="3 3"/>`;
  const hitWidth=(w-left-right)/Math.max(1,rows.length-1);
  rows.forEach((row,i)=>svg+=`<rect x="${xx(i)-hitWidth/2}" y="${top}" width="${Math.max(2,hitWidth)}" height="${h-top-bottom}" fill="transparent" data-id="${row.entity_id}"><title>${esc(titleFor(row))}</title></rect>`);
  svg+=`<text x="${left}" y="${h-4}">${esc(rows[0].event_time.slice(5,16).replace('T',' '))}</text><text x="${w-right}" y="${h-4}" text-anchor="end">${esc(rows.at(-1).event_time.slice(5,16).replace('T',' '))}</text></g></svg>`;
  $('#signal-chart').innerHTML=svg;
  $('.plot-caption span').textContent=isEwma?'EWMA λ=0.2 · time-dependent 3σ limits · exploratory':raw?'Raw anonymous measurements · physical units unavailable':'Training median ±3 SD · clues, not specification limits';
  const rh=65,rmax=Math.max(.1,...rows.map(row=>row.risk))*1.15;
  const ry=value=>5+(rh-17)*(1-value/rmax);
  let risk=`<svg viewBox="0 0 ${w} ${rh}" role="img" aria-label="Frozen model risk with revealed outcomes"><title>Frozen-model risk; orange marks revealed failures</title><g aria-hidden="true"><text x="1" y="12">${pct(rmax,0)}</text><path d="${pathFor(rows.map(row=>row.risk),xx,ry)}" fill="none" stroke="#738dbd" stroke-width="1.1"/>`;
  rows.forEach((row,i)=>{if(row.failed===1)risk+=`<circle cx="${xx(i)}" cy="${ry(row.risk)}" r="2.6" fill="#d66b32"/>`;if(row.decision==='abstain')risk+=`<line x1="${xx(i)}" x2="${xx(i)}" y1="5" y2="${rh-10}" stroke="#a2aebf" stroke-width="1.5"/>`;risk+=`<rect x="${xx(i)-hitWidth/2}" y="0" width="${Math.max(2,hitWidth)}" height="${rh}" fill="transparent" data-id="${row.entity_id}"><title>${esc(titleFor(row))}</title></rect>`});
  $('#risk-chart').innerHTML=risk+'</g></svg>';
  renderHeatmap(rows);renderLedger();
}
function renderHeatmap(rows){
  const entities=rows.slice(-80),signals=state.suggested.slice(0,9),w=760,h=160,left=81,cellW=(w-left-10)/entities.length,cellH=13;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Process fingerprint for the latest ${entities.length} records in the window"><title>Latest ${entities.length} records in the analysis window; missing cells are gray</title><g aria-hidden="true">`;
  signals.forEach((sensor,j)=>{svg+=`<text x="0" y="${j*cellH+13}">${sensor}</text>`;entities.forEach((row,i)=>{const z=zscore(row,sensor);const opacity=z==null?1:Math.min(1,.12+Math.abs(z)/4);const color=z==null?'#dce1eb':z<0?'#7695d9':'#d58c69';svg+=`<rect x="${left+i*cellW}" y="${j*cellH+4}" width="${Math.max(.6,cellW-.7)}" height="${cellH-1}" fill="${color}" opacity="${opacity}" data-id="${row.entity_id}"><title>${row.entity_id} / ${sensor}: ${z==null?'missing':fmt(z,2)+' SD'}</title></rect>`})});
  const selected=entities.findIndex(row=>row.entity_id===state.selected);
  if(selected>=0)svg+=`<rect x="${left+selected*cellW}" y="3" width="${cellW}" height="${signals.length*cellH}" fill="none" stroke="#284d9c" stroke-width="1" pointer-events="none"/>`;
  svg+=`<text x="${left}" y="${h-9}">${esc(entities[0].entity_id)}</text><text x="${w-10}" y="${h-9}" text-anchor="end">latest ${entities.length} in window</text></g></svg>`;
  $('#heatmap').innerHTML=svg;
}
function ledgerRows(){let rows=visibleRows();const search=$('#record-search').value.trim().toLowerCase();if(search)rows=rows.filter(row=>row.entity_id.toLowerCase().includes(search));if(state.filter==='review')rows=rows.filter(row=>row.reason);if(state.filter==='failed')rows=rows.filter(row=>row.failed===1);if(state.filter==='pending')rows=rows.filter(row=>row.failed==null);return [...rows].sort((a,b)=>{const av=a[state.sort],bv=b[state.sort];return (typeof av==='number'?av-bv:String(av).localeCompare(String(bv)))*(state.desc?-1:1)})}
function renderLedger(){
  const all=ledgerRows(),pages=Math.max(1,Math.ceil(all.length/10));state.page=Math.min(state.page,pages-1);
  $('#ledger').innerHTML=all.slice(state.page*10,state.page*10+10).map(row=>`<tr data-id="${row.entity_id}" class="${row.entity_id===state.selected?'selected':''}" tabindex="0" aria-label="Inspect ${row.entity_id}"><td><button class="pin-row ${state.pins.has(row.entity_id)?'pinned':''}" data-pin="${row.entity_id}" aria-label="Pin ${row.entity_id}">${state.pins.has(row.entity_id)?'●':'＋'}</button></td><td class="mono">${row.entity_id}</td><td class="mono">${esc(row.event_time.slice(5,16).replace('T',' '))}</td><td class="mono">${pct(row.risk,2)}</td><td class="mono">${pct(row.missing_fraction)}</td><td>${row.reason?badge(row.status||'open',row.decision==='abstain'?'input hold':'review')+' ':''}${outcome(row.failed)}</td></tr>`).join('')||'<tr><td colspan="6" class="empty">No records match this window and filter.</td></tr>';
  $('#record-count').textContent=`${all.length} matching records · ${state.rows.length} ingested`;
  $('#page-label').textContent=`${state.page+1} / ${pages}`;$('#previous-page').disabled=state.page===0;$('#next-page').disabled=state.page>=pages-1;
}
$('#record-search').oninput=()=>{state.page=0;renderLedger()};
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{state.filter=button.dataset.filter;state.page=0;document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b===button));renderLedger()});
document.querySelectorAll('[data-sort]').forEach(button=>button.onclick=()=>{state.desc=state.sort===button.dataset.sort?!state.desc:true;state.sort=button.dataset.sort;state.page=0;renderLedger()});
$('#previous-page').onclick=()=>{state.page--;renderLedger()};$('#next-page').onclick=()=>{state.page++;renderLedger()};
$('#window-size').onchange=()=>{state.page=0;renderCharts()};$('#window-position').oninput=()=>{$('#follow-latest').checked=false;state.page=0;renderCharts()};$('#follow-latest').onchange=renderCharts;
$('#plot-scale').onchange=async()=>{if($('#plot-scale').value!=='standard'&&state.traces.length>1){state.traces=state.traces.slice(0,1);renderSignalList();toast('Raw-value and EWMA views show one signal. Standardized mode supports overlays.');await refresh().catch(fail)}else renderCharts()};
for(const selector of ['#signal-chart','#risk-chart','#heatmap']){$(selector).onclick=event=>{const cell=event.target.closest('[data-id]');if(cell)selectEntity(cell.dataset.id).catch(fail)};$(selector).onmousemove=event=>{const cell=event.target.closest('[data-id]');if(cell)$('#hover-readout').textContent=cell.dataset.id}}
$('#ledger').onclick=event=>{const pin=event.target.closest('[data-pin]');if(pin){togglePin(pin.dataset.pin).catch(fail);return}const row=event.target.closest('[data-id]');if(row)selectEntity(row.dataset.id).catch(fail)};
$('#ledger').onkeydown=event=>{if(event.key==='Enter'){const row=event.target.closest('[data-id]');if(row)selectEntity(row.dataset.id).catch(fail)}};

async function selectEntity(id){state.selected=id;state.dirty=false;$('#save-state').textContent='';const data=await api('entity/'+encodeURIComponent(id));if(state.selected!==id)return;state.entity=data;renderInspector(data);renderCharts();renderBoard();$('#inspector').scrollTop=0;document.body.classList.add('inspector-open')}
function renderInspector(data,preserve=false){
  $('#inspector-empty').hidden=true;$('#inspector-content').hidden=false;
  $('#entity-title').textContent=data.entity_id;$('#entity-time').textContent=data.event_time.replace('T',' ');
  const outcomeValue=data.outcome.length?data.outcome[0].failed:null,review=data.investigation[0];
  $('#entity-tags').innerHTML=outcome(outcomeValue)+' '+(review?badge(review.status):badge('pending','no investigation'));
  $('#entity-stats').innerHTML=`<div><span>MODEL RISK</span><strong>${pct(data.prediction.risk,2)}</strong></div><div><span>COMPLETENESS</span><strong>${pct(1-data.missing_fraction)}</strong></div>`;
  $('#entity-evidence').innerHTML=data.evidence.slice(0,8).map(e=>{const value=Math.max(-6,Math.min(6,e.z||0)),width=Math.abs(value)/12*100,left=value<0?50-width:50;return `<div class="evidence-row" title="${e.sensor}: ${e.value==null?'missing':e.value}; training median ${e.reference}"><span>${e.sensor}</span><span class="z-track"><i style="left:${left}%;width:${width}%;background:${Math.abs(e.z||0)>3?'#d88757':'#8da7d9'}"></i></span><span class="z-value">${e.z==null?'NA':fmt(e.z,1)}</span></div>`}).join('');
  $('#case-form').hidden=!review;$('#open-review-container').hidden=Boolean(review);
  if(review&&!preserve){$('#case-owner').value=review.owner;$('#case-status').value=review.status;$('#case-note').value=review.note}
  $('#entity-audit').innerHTML=[...data.audit].reverse().map(event=>`<div class="audit-event"><strong>${esc(event.action.replaceAll('_',' '))}</strong><time>${esc(event.created_at)} UTC</time><p>${esc(auditDescription(event))}</p></div>`).join('');
  $('#pin-entity').textContent=state.pins.has(data.entity_id)?'●':'＋';
}
function auditDescription(event){try{const detail=JSON.parse(event.detail);return [detail.status,detail.owner,detail.note].filter(Boolean).join(' · ')}catch{return event.detail}}
$('#case-form').insertAdjacentHTML('beforebegin','<div id="open-review-container" class="inspector-section" hidden><p class="micro">No review exists for this entity. Create a traceable engineering investigation when further verification is needed.</p><button id="open-review">＋ Create engineering review</button></div>');
$('.inspector-heading').insertAdjacentHTML('beforeend','<button id="close-inspector" class="icon-button" aria-label="Close evidence inspector">×</button>');
document.body.insertAdjacentHTML('beforeend','<button id="inspector-backdrop" aria-label="Dismiss evidence inspector"></button>');
$('#close-inspector').onclick=$('#inspector-backdrop').onclick=()=>document.body.classList.remove('inspector-open');
$('#open-review').onclick=async()=>{if(!state.selected)return;try{await post('investigations/'+encodeURIComponent(state.selected));await selectEntity(state.selected);await refresh();toast('Engineering review opened and added to the audit trail.')}catch(error){fail(error)}};
for(const id of ['case-owner','case-status','case-note'])$('#'+id).addEventListener('input',()=>state.dirty=true);
$('#save-case').onclick=async()=>{if(!state.selected)return;try{await api('investigations/'+encodeURIComponent(state.selected),{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({owner:$('#case-owner').value,status:$('#case-status').value,note:$('#case-note').value})});state.dirty=false;await selectEntity(state.selected);$('#save-state').textContent='Saved to audit history.';toast('Handoff saved.');await refresh()}catch(error){fail(error)}};
$('#inspect-latest').onclick=()=>{if(state.rows.length)selectEntity(state.rows.at(-1).entity_id).catch(fail);else toast('Run or step the replay first.')};
$('#next-review').onclick=()=>{const pending=state.cases.filter(item=>item.status!=='resolved').sort((a,b)=>(a.reason==='Data quality gate'?-1:1)-(b.reason==='Data quality gate'?-1:1)||b.event_time.localeCompare(a.event_time));if(!pending.length){toast('No unresolved reviews in this session.');return}const index=pending.findIndex(item=>item.entity_id===state.selected);selectEntity(pending[(index+1)%pending.length].entity_id).catch(fail)};

async function togglePin(id){if(state.pins.has(id))state.pins.delete(id);else{if(state.pins.size>=3){toast('Compare up to three entities. Unpin one to add another.');return}state.pins.set(id,await api('entity/'+encodeURIComponent(id)))}$('#pin-count').textContent=state.pins.size;if(state.selected)$('#pin-entity').textContent=state.pins.has(state.selected)?'●':'＋';renderLedger()}
$('#pin-entity').onclick=()=>{if(state.selected)togglePin(state.selected).catch(fail)};
$('#compare-button').onclick=async()=>{if(state.pins.size<2){toast('Pin at least two entities from the ledger or inspector.');return}try{const entities=await Promise.all([...state.pins.keys()].map(id=>api('entity/'+encodeURIComponent(id))));const sensors=state.suggested.slice(0,9);let html='<table><thead><tr><th>MEASUREMENT</th>'+entities.map(item=>`<th>${item.entity_id}</th>`).join('')+'</tr></thead><tbody>';for(const [name,fn] of [['Outcome',e=>outcome(e.outcome.length?e.outcome[0].failed:null)],['Failure risk',e=>pct(e.prediction.risk,2)],['Missing measurements',e=>pct(e.missing_fraction)],['Review status',e=>esc(e.investigation[0]?.status||'No review')]])html+=`<tr><td>${name}</td>${entities.map(item=>'<td>'+fn(item)+'</td>').join('')}</tr>`;for(const sensor of sensors)html+=`<tr><td class="mono">${sensor}</td>${entities.map(entity=>{const value=entity.evidence.find(item=>item.sensor===sensor);return `<td class="compare-cell"><strong>${fmt(value?.value,3)}</strong><small>${value?.z==null?'Missing':fmt(value.z,2)+' SD from reference'}</small></td>`}).join('')}</tr>`;$('#compare-content').innerHTML=html+'</tbody></table>';$('#compare-dialog').showModal()}catch(error){fail(error)}};

function renderBoard(){const reason=$('#review-reason').value,owner=$('#review-owner').value.toLowerCase();const cases=state.cases.filter(item=>(reason==='all'||item.reason===reason)&&item.owner.toLowerCase().includes(owner));$('#review-board').innerHTML=['open','investigating','resolved'].map(status=>{const items=cases.filter(item=>item.status===status).sort((a,b)=>(a.reason==='Data quality gate'?0:1)-(b.reason==='Data quality gate'?0:1)||b.event_time.localeCompare(a.event_time));return `<section class="board-lane"><div class="lane-heading">${status.toUpperCase()}<span>${items.length}</span></div>${items.map(item=>`<button class="review-card ${item.reason==='Data quality gate'?'hold':''} ${item.entity_id===state.selected?'selected':''}" data-case="${item.entity_id}" aria-label="Review ${item.entity_id}"><div class="review-card-head"><strong>${item.entity_id}</strong>${outcome(item.failed)}</div><p>${esc(item.reason)}</p><p>Risk ${pct(item.risk,2)} · ${esc(item.event_time.slice(5,16).replace('T',' '))}</p><div class="review-card-foot"><span>${esc(item.owner)}</span><span>Inspect →</span></div></button>`).join('')||'<div class="lane-empty">No matching reviews</div>'}</section>`}).join('')}
$('#review-reason').insertAdjacentHTML('beforeend','<option>Engineer review</option>');$('#review-reason').onchange=renderBoard;$('#review-owner').oninput=renderBoard;$('#review-board').onclick=event=>{const card=event.target.closest('[data-case]');if(card)selectEntity(card.dataset.case).catch(fail)};

function renderQuality(){const search=$('#quality-search').value.toLowerCase(),key=$('#quality-sort').value;const signals=state.catalog.filter(item=>item.sensor.includes(search)).sort((a,b)=>b[key]-a[key]);$('#quality-rows').innerHTML=signals.map(signal=>`<tr><td class="mono">${signal.sensor}</td><td>${pct(signal.training_missing_fraction)}</td><td>${pct(signal.missing_fraction)}</td><td>${signal.training_distinct}</td><td>${fmt(signal.training_effect_abs,3)}</td><td><button data-plot="${signal.sensor}" aria-label="Analyze ${signal.sensor}">Plot ↗</button></td></tr>`).join('');$('#gate-note').textContent='Records above 15% missingness are held for data quality review. Reference signals are selected on training data only.'}
$('#quality-search').oninput=renderQuality;$('#quality-sort').onchange=renderQuality;$('#quality-rows').onclick=async event=>{const button=event.target.closest('[data-plot]');if(!button)return;state.traces=[button.dataset.plot];$('#plot-scale').value='native';renderSignalList();switchView('workbench');await refresh().catch(fail)};
let modelCache;
async function loadModel(){const data=modelCache||await api('model');modelCache=data;$('#model-metrics').innerHTML=[['TEST AVERAGE PRECISION',fmt(data.test.ap,4),'Test prevalence '+pct(data.splits.test.fails/data.splits.test.n)],['FAILURES DETECTED',data.test.tp+' / '+data.splits.test.fails,'At the declared frozen threshold'],['ROC AUC',fmt(data.test.roc_auc,4),'Chronological final test'],['WARM PIPELINE P95',fmt(data.latency_ms.p95,2)+' ms','Excludes HTTP, SQL, explanations']].map(([a,b,c])=>`<div><span>${a}</span><strong>${b}</strong><small>${c}</small></div>`).join('');$('#split-track').innerHTML=Object.entries(data.splits).map(([name,split])=>`<div class="split-segment" style="flex:${split.n}"><strong>${name.toUpperCase()}</strong><span>${split.n}</span><small>${split.fails} failures</small></div>`).join('');$('#model-candidates').innerHTML='<table><thead><tr><th>CANDIDATE</th><th>POLICY AP</th><th>BRIER</th></tr></thead><tbody>'+data.candidates.map(item=>`<tr><td>${item.name===data.winner.name?'✓ ':''}${item.name}</td><td>${fmt(item.policy_ap,4)}</td><td>${fmt(item.policy_brier,4)}</td></tr>`).join('')+'</tbody></table>';$('#model-findings').innerHTML=`<div><strong>Cost policy:</strong> missed failure = 10 hypothetical units; false review = 1 unit.</div><div><strong>Original result:</strong> ${data.test.fn} missed failures, ${data.test.fp} false reviews. No validated cost reduction.</div><div><strong>AP uncertainty:</strong> day-block bootstrap 95% interval ${fmt(data.bootstrap_95_ci.ap[0],4)}–${fmt(data.bootstrap_95_ci.ap[1],4)}.</div><div><strong>Follow-up:</strong> the exploratory challenger uses an already-inspected test period and is not promoted.</div><div><strong>Next validation:</strong> a new future or site holdout and engineer-reviewed shadow evaluation.</div>`}

function csvValue(value){let text=String(value??'');if(typeof value==='string'&&/^\s*[=+@-]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"'}
$('#export-records').onclick=()=>{const rows=ledgerRows();if(!rows.length){toast('No matching records to export.');return}const fields=['entity_id','event_time','risk','missing_fraction','decision','failed','reason','status',...state.traces];const text=[fields.map(csvValue).join(','),...rows.map(row=>fields.map(field=>csvValue(field.startsWith('sensor_')?row.signals[field]:row[field])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download='fabwatch-visible-records.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(`${rows.length} matching records exported with selected signals.`)};

function stopReplay(){state.playing=false;clearTimeout(state.timer);$('#play').textContent='▶ Run replay';$('#step').disabled=false;$('#stream-status').textContent=state.overview?.replay.cursor===state.overview?.replay.total?'Complete':'Paused'}
async function advance(){if(state.busy)return;state.busy=true;$('#step').disabled=true;try{await post('replay/step?count='+$('#replay-speed').value);await refresh();if(state.overview.replay.cursor===state.overview.replay.total)stopReplay()}catch(error){fail(error)}finally{state.busy=false;$('#step').disabled=state.playing||state.overview?.replay.cursor===state.overview?.replay.total;if(state.playing)state.timer=setTimeout(advance,1000)}}
$('#step').onclick=advance;$('#play').onclick=()=>{if(state.playing){stopReplay();return}if(state.overview?.replay.cursor===state.overview?.replay.total){toast('Replay complete. Start a new session to run again.');return}state.playing=true;$('#play').textContent='Ⅱ Pause replay';$('#stream-status').textContent='Running';$('#step').disabled=true;advance()};
$('#replay-speed').onchange=()=>$('#step').textContent='Step +'+$('#replay-speed').value;
function clearSessionUI(){state.selected=null;state.entity=null;state.pins.clear();state.page=0;state.dirty=false;$('#pin-count').textContent='0';$('#inspector-empty').hidden=false;$('#inspector-content').hidden=true;$('#follow-latest').checked=true;document.body.classList.remove('inspector-open')}
$('#new-session').onclick=async()=>{stopReplay();try{await post('replay/new');clearSessionUI();await refresh();await loadSessions();toast('New replay ready. The previous warehouse is preserved in Sessions.')}catch(error){fail(error)}};
$('#session-label').innerHTML='<label for="session-select">Session </label><select id="session-select" aria-label="Select preserved replay session"></select>';
async function loadSessions(){state.sessions=await api('replay/sessions');$('#session-select').innerHTML=state.sessions.map(item=>`<option value="${esc(item.session)}" ${item.current?'selected':''}>${esc(item.session)}</option>`).join('')}
$('#session-select').onchange=async()=>{stopReplay();try{await api('replay/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:$('#session-select').value})});clearSessionUI();await refresh();toast('Preserved warehouse restored.')}catch(error){fail(error)}};

async function refresh(){
  const id=++state.refreshId;const requested=[...new Set([...state.traces,...state.suggested.slice(0,9)])];
  const [overview,analysis,cases]=await Promise.all([api('overview'),api('analysis?signals='+requested.join(',')),api('investigations')]);
  if(id!==state.refreshId)return;if(state.analysis&&state.analysis.session!==analysis.session)clearSessionUI();state.overview=overview;state.analysis=analysis;state.rows=analysis.rows;state.cases=cases;state.lastSync=Date.now();
  $('#error').hidden=true;$('#error').textContent='';$('#connection-dot').classList.remove('offline');$('#connection').textContent='Local API connected';$('#freshness').textContent='Synced just now';
  $('#metric-scored').textContent=overview.summary.scored;$('#metric-yield').textContent=pct(overview.summary.yield);$('#metric-outcomes').textContent=`${overview.summary.known} / ${overview.summary.scored-overview.summary.known}`;$('#metric-holds').textContent=overview.summary.abstentions;$('#metric-open').textContent=cases.filter(item=>item.status!=='resolved').length;$('#nav-count').textContent=cases.length;
  $('#source-time').textContent=analysis.latest_event?'Source test time '+analysis.latest_event.replace('T',' '):'Waiting for source records';$('#replay-progress').textContent=`${overview.replay.cursor} / ${overview.replay.total}`;$('#replay-bar').value=overview.replay.cursor;$('#stream-status').textContent=state.playing?'Running':overview.replay.cursor===overview.replay.total?'Complete':'Paused';$('#play').disabled=overview.replay.cursor===overview.replay.total;$('#step').disabled=state.playing||overview.replay.cursor===overview.replay.total;
  if(!state.playing)$('#play').textContent=overview.replay.cursor===overview.replay.total?'✓ Replay complete':'▶ Run replay';
  renderCharts();renderBoard();
  if(state.selected){const selected=state.selected;const entity=await api('entity/'+encodeURIComponent(selected));if(state.selected===selected){state.entity=entity;renderInspector(entity,state.dirty)}}
  if(overview.replay.cursor===overview.replay.total&&state.playing)stopReplay();
}
async function boot(){const data=await api('signals');state.catalog=data.signals;state.suggested=data.suggested;state.traces=state.suggested.slice(0,3);renderSignalList();await refresh();await loadSessions();if(window.matchMedia('(min-width:901px)').matches){if(state.cases.length)await selectEntity(state.cases[0].entity_id);else if(state.rows.length)await selectEntity(state.rows.at(-1).entity_id)}}
boot().catch(fail);
setInterval(()=>{if(!state.busy&&!state.playing)refresh().catch(fail)},4000);
setInterval(()=>{if(state.lastSync){const seconds=Math.round((Date.now()-state.lastSync)/1000);$('#freshness').textContent=seconds<2?'Synced just now':`Synced ${seconds}s ago`}},1000);
