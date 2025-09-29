document.addEventListener('DOMContentLoaded', () => {
  /*** Config ***/
  const ENDPOINT = "https://vanity-plate.profit-alerts.workers.dev/api/validate";
  const PROXY_KEY = "";
  const CHECK_DELAY_MS = 1200;
  const REFRESH_CUTOFF_HOURS = 24;

  /*** Utils ***/
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const sleep = ms => new Promise(r=>setTimeout(r,ms));
  function relTime(iso){
    if(!iso) return "—";
    const then = new Date(iso), now = new Date();
    const s = Math.floor((now - then)/1000);
    const m = Math.floor(s/60), h = Math.floor(m/60), d = Math.floor(h/24);
    if (s < 60) return s + "s ago";
    if (m < 60) return m + "m ago";
    if (h < 24) return h + "h ago";
    return d + "d ago";
  }
  function debounce(fn, wait=120){ let to; return (...a)=>{ clearTimeout(to); to=setTimeout(()=>fn(...a), wait); } }

  /*** Normalize plate text ***/
  function normalizePlateText(s){
    return String(s||"").toUpperCase().replace(/O/g,'0').replace(/[^A-Z0-9]/g,'').slice(0,7);
  }

  /*** Storage (plates) ***/
  const STORAGE_KEY = "plates_v1";
  function loadPlates(){ try{ const raw=localStorage.getItem(STORAGE_KEY); if(!raw) return []; const arr=JSON.parse(raw); return Array.isArray(arr)?arr:[]; }catch{ return []; } }
  function savePlates(arr){
    arr.sort((a,b)=>(a.plateText||"").localeCompare(b.plateText||"","en",{sensitivity:"base"}));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(arr));
  }
  function mkKey(p){ return [(p.plateText||"").toUpperCase(), p.selectedVehicleType||"PassengerVehicle", p.selectedKindOfPlate||"Personalized", p.selectedPlateProgram||"Select", p.selectedPlateProgramID||"", p.selectedPlateProgramSubCategory||"Select"].join("|"); }
  function upsertPlate(entry){
    const list=loadPlates(); const key=mkKey(entry);
    const i=list.findIndex(p=>mkKey(p)===key);
    if(i>=0) list[i]={...list[i],...entry}; else list.push(entry);
    savePlates(list); return list;
  }

  /*** Migrate ***/
  (function migrate(){
    const list=loadPlates(); let changed=false;
    for(const p of list){
      const n=normalizePlateText(p.plateText); if(n!==p.plateText){p.plateText=n; changed=true;}
      p.selectedVehicleType=p.selectedVehicleType||"PassengerVehicle";
      p.selectedKindOfPlate=p.selectedKindOfPlate||"Personalized";
      p.selectedPlateProgram=p.selectedPlateProgram||"Select";
      p.selectedPlateProgramID=p.selectedPlateProgramID||"";
      p.selectedPlateProgramSubCategory=p.selectedPlateProgramSubCategory||"Select";
    }
    if(changed) savePlates(list);
  })();

  /*** Proxy ***/
  async function postValidate(payload){
    const headers={"Content-Type":"application/json","Accept":"application/json"};
    if(PROXY_KEY) headers["x-proxy-key"]=PROXY_KEY;
    const res=await fetch(ENDPOINT,{method:"POST",headers,body:JSON.stringify(payload)});
    const text=await res.text(); let data;
    try{ data=JSON.parse(text); }catch{ throw new Error(`Non-JSON response (${res.status}): ${text.slice(0,200)}`); }
    if(!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return !!data.Available;
  }
  function basePayload(p){ return { plateText:p.plateText, selectedVehicleType:"PassengerVehicle", selectedKindOfPlate:"Personalized", selectedPlateProgram:"Select", selectedPlateProgramID:"", selectedPlateProgramSubCategory:"Select" }; }

  /*** Status helpers ***/
  function isDue(p){ if(!p.lastCheckedUtc) return true; const t=Date.parse(p.lastCheckedUtc); if(Number.isNaN(t)) return true; return (Date.now()-t)>=REFRESH_CUTOFF_HOURS*3600*1000; }
  function markChecked(p,status,note){ const ts=new Date().toISOString(); p.lastStatus=status; p.lastCheckedUtc=ts; p.history=p.history||[]; const e={status,checkedUtc:ts}; if(note) e.note=note; p.history.push(e); }
  function statusClass(s){ if(s==="Available")return"available"; if(s==="Unavailable")return"unavailable"; if(s==="Error")return"error"; if(s==="Unknown"||!s)return"unknown"; return"unknown"; }

  /*** Fit text ***/
  function fitTileText(el){
    const parent=el.parentElement; if(!parent) return;
    el.style.transform='scale(1)';
    const maxW=Math.max(1,parent.clientWidth-8);
    const maxH=Math.max(1,parent.clientHeight-6);
    const needW=Math.max(1,el.scrollWidth);
    const needH=Math.max(1,el.scrollHeight);
    const scale=Math.min(1,maxW/needW,maxH/needH);
    el.style.transform=`scale(${scale})`;
  }
  function fitAll(){ $$('#board .fit').forEach(fitTileText); const t=document.getElementById('titleFit'); if(t) fitTileText(t); }
  window.addEventListener('resize', debounce(fitAll,120));

  /*** Zoom persistence ***/
  const ZOOM_KEY = "plates_zoom_v1";
  const ZOOM_MIN = 40;   // matches input[min]
  const ZOOM_MAX = 180;  // matches input[max]
  function clampZoom(v){
    const n = Number(v);
    if (Number.isNaN(n)) return 100;
    return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, n));
  }
  function setZoom(valPct){
    const clamped = clampZoom(valPct);
    const scale = clamped / 100;
    document.documentElement.style.setProperty('--zoom', scale);
    const slider = document.getElementById('zoom');
    if (slider) slider.value = String(clamped);
    localStorage.setItem(ZOOM_KEY, String(clamped));
    requestAnimationFrame(fitAll);
  }
  function getSavedZoom(){
    const raw = localStorage.getItem(ZOOM_KEY);
    if (raw == null) return null;
    return clampZoom(raw);
  }

  /*** Render ***/
  function render(){
    const rows=loadPlates();
    const q=$("#q").value.trim().toLowerCase();
    const st=$("#status").value;

    const filtered=rows.filter(r=>{
      const mq=!q || (r.plateText||"").toLowerCase().includes(q);
      const ms=!st || (r.lastStatus||"Unknown")===st;
      return mq && ms;
    });

    const latest=rows.reduce((a,b)=>{ const ta=a?.lastCheckedUtc?Date.parse(a.lastCheckedUtc):0; const tb=b?.lastCheckedUtc?Date.parse(b.lastCheckedUtc):0; return tb>ta?b:a; },null);
    $("#updated").textContent = latest?.lastCheckedUtc ? `latest: ${relTime(latest.lastCheckedUtc)}` : "no checks yet";

    const html=filtered.map(r=>{
      const cls=statusClass(r.lastStatus||"Unknown");
      const statusLabel=r.lastStatus||"Unknown";
      const when=r.lastCheckedUtc?relTime(r.lastCheckedUtc):"—";
      const plateText=normalizePlateText(r.plateText);
      const key=mkKey(r);
      return `<div class="plate ${cls}" data-key="${key}">
        <div class="face"></div>
        <div class="bolts"></div><div class="bolts btm"></div>
        <div class="top"><div class="state">IDAHO</div><div class="status ${cls}">${statusLabel}</div></div>
        <div class="text" title="${plateText}"><span class="fit">${plateText}</span></div>
        <div class="bottom"><div class="ago" title="${r.lastCheckedUtc?new Date(r.lastCheckedUtc).toLocaleString():""}">${when}</div></div>
        <div class="delete-overlay" data-action="delete" data-key="${key}">
          <button class="delete-button" data-action="delete" data-key="${key}" title="Delete plate">🗑 Delete Plate</button>
        </div>
      </div>`;
    }).join("");

    $("#board").innerHTML = html || `<div class="pill" style="margin:12px auto">No plates yet. Click “Add Plate”.</div>`;
    requestAnimationFrame(fitAll);
  }

  /*** Refresh flow ***/
  function setRunStatus(txt){ const el=$("#runStatus"); if(!txt){el.style.display="none"; el.textContent=""; return;} el.style.display="inline-block"; el.textContent=txt; }
  async function refreshDue({force=false}={}){
    const btn=$("#refresh"); if(!btn) return;
    const all=loadPlates();
    const targets=force?all:all.filter(isDue);
    if(targets.length===0){ setRunStatus("Up to date"); setTimeout(()=>setRunStatus(""),1200); return; }
    btn.disabled=true; const label=btn.textContent; btn.textContent="Refreshing…"; setRunStatus(`0/${targets.length}`);
    let i=0;
    for(const p of targets){
      try{ const a=await postValidate(basePayload(p)); markChecked(p, a?"Available":"Unavailable"); }
      catch(e){ markChecked(p,"Error",String(e?.message||e)); }
      savePlates(all); render(); i++; setRunStatus(`${i}/${targets.length}`); if(i<targets.length) await sleep(CHECK_DELAY_MS);
    }
    btn.textContent=label; btn.disabled=false; setRunStatus("Done"); setTimeout(()=>setRunStatus(""),1200);
  }

  /*** Modals ***/
  function openModal(sel){ const m=$(sel); if(m) m.style.display='flex'; }
  function closeModal(sel){ const m=$(sel); if(m) m.style.display='none'; }

  /*** Add Plate ***/
  $("#addPlateBtn").addEventListener("click", ()=> openModal('#modal'));
  $("#m_cancel").addEventListener("click", ()=> closeModal('#modal'));
  $("#m_plateText").addEventListener('input', e=>{
    const caret=e.target.selectionStart ?? e.target.value.length;
    const normalized=normalizePlateText(e.target.value);
    e.target.value=normalized;
    e.target.selectionStart=e.target.selectionEnd=Math.min(caret, normalized.length);
  });
  function validatePlateText(s){ const t=normalizePlateText(s); if(!t) throw new Error("plateText must be 1–7 letters/numbers"); return t; }
  $("#m_submit").addEventListener("click", async ()=>{
    const msg=$("#m_msg"); msg.textContent="";
    try{
      const entry={ plateText:validatePlateText($("#m_plateText").value), selectedVehicleType:"PassengerVehicle", selectedKindOfPlate:"Personalized", selectedPlateProgram:"Select", selectedPlateProgramID:"", selectedPlateProgramSubCategory:"Select", lastStatus:"Unknown", lastCheckedUtc:null, history:[] };
      msg.textContent="Checking…";
      try{ const avail=await postValidate(basePayload(entry)); markChecked(entry, avail?"Available":"Unavailable"); msg.textContent="Saved."; }
      catch(e){ markChecked(entry,"Error",String(e?.message||e)); msg.textContent="Saved (check failed)."; }
      upsertPlate(entry); render(); setTimeout(()=>closeModal('#modal'),700);
    }catch(e){ msg.textContent="Error: "+e.message; }
  });

  /*** Confirm refresh ***/
  $("#refresh").addEventListener("click", ()=> openModal('#confirmModal'));
  $("#cfm_cancel").addEventListener("click", ()=> closeModal('#confirmModal'));
  $("#cfm_due").addEventListener("click", async ()=>{ closeModal('#confirmModal'); await refreshDue({force:false}); });
  $("#cfm_force").addEventListener("click", async ()=>{ closeModal('#confirmModal'); await refreshDue({force:true}); });

  /*** Delete flow ***/
  let pendingDeleteKey=null;
  function openDeleteModalByKey(key){
    pendingDeleteKey=key;
    const p=loadPlates().find(x=>mkKey(x)===key);
    const label=document.getElementById('delLabel'); if(label) label.textContent=p?normalizePlateText(p.plateText):'this plate';
    openModal('#deleteModal');
  }
  function deleteByKey(key){ const arr=loadPlates().filter(p=>mkKey(p)!==key); savePlates(arr); render(); }
  const boardEl=document.getElementById('board');
  if(boardEl){
    boardEl.addEventListener('click', e=>{
      const t=e.target.closest('[data-action="delete"]'); if(!t) return;
      const key=t.getAttribute('data-key'); openDeleteModalByKey(key);
    });
  }
  $("#del_cancel")?.addEventListener('click', ()=> closeModal('#deleteModal'));
  $("#del_confirm")?.addEventListener('click', ()=>{ if(pendingDeleteKey){ deleteByKey(pendingDeleteKey); pendingDeleteKey=null; } closeModal('#deleteModal'); });

  /*** Import/Export & Filters ***/
  $("#q").addEventListener("input", render);
  $("#status").addEventListener("change", render);
  $("#exportBtn").addEventListener("click", ()=>{
    const blob=new Blob([localStorage.getItem(STORAGE_KEY)||"[]"],{type:"application/json"});
    const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="plates-export.json"; a.click(); URL.revokeObjectURL(a.href);
  });
  $("#importFile").addEventListener("change", async e=>{
    const f=e.target.files?.[0]; if(!f) return;
    const text=await f.text();
    try{
      const arr=JSON.parse(text); if(!Array.isArray(arr)) throw new Error("Invalid JSON");
      arr.forEach(p=>{ if(p.plateText) p.plateText=normalizePlateText(p.plateText);
        p.selectedVehicleType=p.selectedVehicleType||"PassengerVehicle";
        p.selectedKindOfPlate=p.selectedKindOfPlate||"Personalized";
        p.selectedPlateProgram=p.selectedPlateProgram||"Select";
        p.selectedPlateProgramID=p.selectedPlateProgramID||"";
        p.selectedPlateProgramSubCategory=p.selectedPlateProgramSubCategory||"Select";
      });
      savePlates(arr); render(); e.target.value="";
    }catch(err){ alert("Import failed: "+err.message); }
  });

  /*** Zoom: load saved, wire slider, then fit ***/
  (function initZoom(){
    const slider = document.getElementById('zoom');
    const saved = getSavedZoom();
    if (saved != null) setZoom(saved);
    else if (slider) setZoom(Number(slider.value) || 100);
    slider?.addEventListener('input', e => setZoom(e.target.value));
  })();

  /*** Header date ***/
  (function setHeaderDate(){ const el=document.getElementById('hdrDate'); if(!el) return; const now=new Date(); el.textContent = now.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric'}); })();

  /*** Start ***/
  requestAnimationFrame(fitAll);
  (function init(){
    if(loadPlates().length===0){
      savePlates([{ plateText:"SWAG", selectedVehicleType:"PassengerVehicle", selectedKindOfPlate:"Personalized", selectedPlateProgram:"Select", selectedPlateProgramID:"", selectedPlateProgramSubCategory:"Select", lastStatus:"Unknown", lastCheckedUtc:null, history:[] }]);
    }
    render();
    refreshDue({force:false});
  })();
}); // DOMContentLoaded
