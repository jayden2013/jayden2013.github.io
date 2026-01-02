document.addEventListener('DOMContentLoaded', () => {
  /*** Config ***/
  // IDAHO proxy you already have (returns { Available: boolean })
  const ID_ENDPOINT = "https://vanity-plate.profit-alerts.workers.dev/api/validate";
  const PROXY_KEY = ""; // optional shared secret header

  // NEW: California proxy (must be a simple server/worker you own).
  // It should accept JSON { plateText } and return { Available: boolean }.
  // Leave blank to see a helpful error in the UI.
  const CA_PROXY = "https://vanity-plate-ca.profit-alerts.workers.dev/api/validate-ca"; // e.g., "https://your-worker.example.com/api/validate-ca"

  const CHECK_DELAY_MS = 1200;

  /*** Utils ***/
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const sleep = ms => new Promise(r=>setTimeout(r,ms));
  function relTime(iso){
    if(!iso) return "—";
    const then = new Date(iso), now = new Date();
    const s = Math.floor((now - then)/1000);
    if (s < 5) return "Just now";
    const m = Math.floor(s/60), h = Math.floor(m/60), d = Math.floor(h/24);
    if (s < 60) return s + "s ago";
    if (m < 60) return m + "m ago";
    if (h < 24) return h + "h ago";
    return d + "d ago";
  }
  function debounce(fn, wait=120){ let to; return (...a)=>{ clearTimeout(to); to=setTimeout(()=>fn(...a), wait); } }

  /*** Plate text ***/
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
  function mkKey(p){ return [ (p.plateText||"").toUpperCase(), p.state||"ID", p.selectedVehicleType||"PassengerVehicle", p.selectedKindOfPlate||"Personalized", p.selectedPlateProgram||"Select", p.selectedPlateProgramID||"", p.selectedPlateProgramSubCategory||"Select" ].join("|"); }
  function upsertPlate(entry){
    const list=loadPlates(); const key=mkKey(entry);
    const i=list.findIndex(p=>mkKey(p)===key);
    if(i>=0) list[i]={...list[i],...entry}; else list.push(entry);
    savePlates(list); return list;
  }

  /*** One-time migration: add state=ID to old entries ***/
  (function migrate(){
    const list=loadPlates(); let changed=false;
    for(const p of list){
      const n=normalizePlateText(p.plateText); if(n!==p.plateText){p.plateText=n; changed=true;}
      p.state = p.state || "ID";
      p.selectedVehicleType=p.selectedVehicleType||"PassengerVehicle";
      p.selectedKindOfPlate=p.selectedKindOfPlate||"Personalized";
      p.selectedPlateProgram=p.selectedPlateProgram||"Select";
      p.selectedPlateProgramID=p.selectedPlateProgramID||"";
      p.selectedPlateProgramSubCategory=p.selectedPlateProgramSubCategory||"Select";
    }
    if(changed) savePlates(list);
  })();

  /*** Idaho check (your existing proxy) ***/
  async function postValidateID(payload){
    const headers={"Content-Type":"application/json","Accept":"application/json"};
    if(PROXY_KEY) headers["x-proxy-key"]=PROXY_KEY;
    const res=await fetch(ID_ENDPOINT,{method:"POST",headers,body:JSON.stringify(payload)});
    const text=await res.text(); let data;
    try{ data=JSON.parse(text); }catch{ throw new Error(`Non-JSON response (${res.status}): ${text.slice(0,200)}`); }
    if(!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return !!data.Available;
  }
  function basePayloadID(p){ return { plateText:p.plateText, selectedVehicleType:"PassengerVehicle", selectedKindOfPlate:"Personalized", selectedPlateProgram:"Select", selectedPlateProgramID:"", selectedPlateProgramSubCategory:"Select" }; }

  /*** California check (via your proxy) ***/
  async function postValidateCA(plateText){
    if (!CA_PROXY) {
      throw new Error("California requires a simple proxy. Set CA_PROXY in app.js.");
    }
    const headers={"Content-Type":"application/json","Accept":"application/json"};
    if(PROXY_KEY) headers["x-proxy-key"]=PROXY_KEY;
    const res=await fetch(CA_PROXY,{method:"POST",headers,body:JSON.stringify({ plateText })});
    const text=await res.text(); let data;
    try{ data=JSON.parse(text); }catch{ throw new Error(`CA proxy non-JSON (${res.status}): ${text.slice(0,200)}`); }
    if(!res.ok) throw new Error(data.error || `CA proxy HTTP ${res.status}`);
    return !!data.Available;
  }

  /*** High-level status helpers ***/
  function isDue(p){
    if(!p.lastCheckedUtc) return true;
    const last = new Date(p.lastCheckedUtc);
    if(Number.isNaN(last.getTime())) return true;
    const now = new Date();
    // Refresh if current month or year is different from last check (resets on the 1st)
    return last.getMonth() !== now.getMonth() || last.getFullYear() !== now.getFullYear();
  }
  function markChecked(p,status,note){ const ts=new Date().toISOString(); p.lastStatus=status; p.lastCheckedUtc=ts; p.history=p.history||[]; const e={status,checkedUtc:ts}; if(note) e.note=note; p.history.push(e); }
  function statusClass(s){ if(s==="Available")return"available"; if(s==="Unavailable")return"unavailable"; if(s==="Error")return"error"; if(s==="Unknown"||!s)return"unknown"; return"unknown"; }

  /*** Route to correct checker ***/
  async function checkAvailability(p){
    if ((p.state||"ID") === "CA") {
      const a = await postValidateCA(p.plateText);
      return a ? "Available" : "Unavailable";
    } else {
      const a = await postValidateID(basePayloadID(p));
      return a ? "Available" : "Unavailable";
    }
  }

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

  /*** Render ***/
  function render(){
    const rows=loadPlates();
    const q=$("#q").value.trim().toLowerCase();
    const st=$("#status").value;
    const sf=$("#stateFilter")?.value || ""; // <-- NEW: state filter value

    const filtered=rows.filter(r=>{
      const mq=!q || (r.plateText||"").toLowerCase().includes(q);
      const ms=!st || (r.lastStatus||"Unknown")===st;
      const mstate=!sf || (r.state||"ID")===sf; // <-- NEW: apply state filter
      return mq && ms && mstate;
    });

    const latest=rows.reduce((a,b)=>{ const ta=a?.lastCheckedUtc?Date.parse(a.lastCheckedUtc):0; const tb=b?.lastCheckedUtc?Date.parse(b.lastCheckedUtc):0; return tb>ta?b:a; },null);
    $("#updated").textContent = latest?.lastCheckedUtc ? `latest: ${relTime(latest.lastCheckedUtc)}` : "no checks yet";

    const html=filtered.map(r=>{
      const cls=statusClass(r.lastStatus||"Unknown");
      const statusLabel=r.lastStatus||"Unknown";
      const when=r.lastCheckedUtc?relTime(r.lastCheckedUtc):"—";
      const plateText=normalizePlateText(r.plateText);
      const key=mkKey(r);
      const stateLabel = (r.state==="CA" ? "CALIFORNIA" : "IDAHO");
      return `<div class="plate ${cls}" data-key="${key}">
        <div class="face"></div>
        <div class="bolts"></div><div class="bolts btm"></div>
        <div class="top"><div class="state">${stateLabel}</div><div class="status ${cls}">${statusLabel}</div></div>
        <div class="text" title="${plateText}"><span class="fit">${plateText}</span></div>
        <div class="bottom"><div class="ago" title="${r.lastCheckedUtc?new Date(r.lastCheckedUtc).toLocaleString():""}">${when}</div></div>
        <div class="plate-actions">
          <button class="plate-action-btn refresh" data-action="refresh" data-key="${key}">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> Refresh Plate
          </button>
          <button class="plate-action-btn delete" data-action="delete" data-key="${key}">Delete Plate</button>
        </div>
      </div>`;
    }).join("");

    $("#board").innerHTML = html || `<div class="flex flex-col items-center justify-center py-12"><div class="text-slate-500 mb-4">No plates yet.</div><button id="emptyAddBtn" class="px-6 py-2 rounded-lg bg-[var(--accent)] text-white font-bold shadow-lg hover:opacity-90 transition-all">Add a Plate</button></div>`;
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
      try{ const status = await checkAvailability(p); markChecked(p, status); }
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
      const entry={
        plateText:validatePlateText($("#m_plateText").value),
        state: ($("#m_state").value || "ID"),
        selectedVehicleType:"PassengerVehicle",
        selectedKindOfPlate:"Personalized",
        selectedPlateProgram:"Select",
        selectedPlateProgramID:"",
        selectedPlateProgramSubCategory:"Select",
        lastStatus:"Unknown",
        lastCheckedUtc:null,
        history:[]
      };
      msg.textContent="Checking…";
      try{ const status = await checkAvailability(entry); markChecked(entry, status); msg.textContent="Saved."; }
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
    boardEl.addEventListener('click', async e=>{
      // Handle Delete
      const delBtn=e.target.closest('[data-action="delete"]'); 
      if(delBtn) {
        const key=delBtn.getAttribute('data-key'); 
        openDeleteModalByKey(key);
        return;
      }
      
      // Handle Refresh
      const refBtn=e.target.closest('[data-action="refresh"]');
      if(refBtn){
        const key=refBtn.getAttribute('data-key');
        const p=loadPlates().find(x=>mkKey(x)===key);
        if(!p) return;
        
        // UI Feedback
        refBtn.innerHTML = `<svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> Checking...`;
        refBtn.disabled = true;
        refBtn.style.opacity = '0.7';
        const card = refBtn.closest('.plate');
        if(card) card.style.opacity = '0.6';

        try {
          const status = await checkAvailability(p);
          markChecked(p, status);
        } catch(err) {
          markChecked(p, "Error", String(err?.message||err));
        }
        upsertPlate(p); // Save and re-render
        render();
      }

      // Handle Empty State Add Button
      if(e.target.id === 'emptyAddBtn') {
        $("#addPlateBtn").click();
      }
    });
  }
  $("#del_cancel")?.addEventListener('click', ()=> closeModal('#deleteModal'));
  $("#del_confirm")?.addEventListener('click', ()=>{ if(pendingDeleteKey){ deleteByKey(pendingDeleteKey); pendingDeleteKey=null; } closeModal('#deleteModal'); });

  /*** Import/Export & Filters ***/
  $("#q").addEventListener("input", render);
  $("#status").addEventListener("change", render);
  $("#stateFilter")?.addEventListener("change", render); // <-- NEW: re-render on state select
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
        p.state = p.state || "ID";
        p.selectedVehicleType=p.selectedVehicleType||"PassengerVehicle";
        p.selectedKindOfPlate=p.selectedKindOfPlate||"Personalized";
        p.selectedPlateProgram=p.selectedPlateProgram||"Select";
        p.selectedPlateProgramID=p.selectedPlateProgramID||"";
        p.selectedPlateProgramSubCategory=p.selectedPlateProgramSubCategory||"Select";
      });
      savePlates(arr); render(); e.target.value="";
    }catch(err){ alert("Import failed: "+err.message); }
  });

  /*** Zoom persistence (unchanged from last update) ***/
  const ZOOM_KEY = "plates_zoom_v1";
  const ZOOM_MIN = 40; const ZOOM_MAX = 180;
  function clampZoom(v){ const n=Number(v); if(Number.isNaN(n)) return 100; return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, n)); }
  function setZoom(valPct){ const clamped=clampZoom(valPct); const scale=clamped/100; document.documentElement.style.setProperty('--zoom', scale); const slider=$("#zoom"); if(slider) slider.value=String(clamped); localStorage.setItem(ZOOM_KEY, String(clamped)); requestAnimationFrame(fitAll); }
  function getSavedZoom(){ const raw=localStorage.getItem(ZOOM_KEY); if(raw==null) return null; return clampZoom(raw); }
  (function initZoom(){ const slider=$("#zoom"); const saved=getSavedZoom(); if(saved!=null) setZoom(saved); else if(slider) setZoom(Number(slider.value)||100); slider?.addEventListener('input', e=> setZoom(e.target.value)); })();

  /*** Header date ***/
  (function setHeaderDate(){ const el=document.getElementById('hdrDate'); if(!el) return; const now=new Date(); el.textContent = now.toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric',year:'numeric'}); })();

  /*** Start ***/
  requestAnimationFrame(fitAll);
  (function init(){
    render();
    refreshDue({force:false});
  })();
}); // DOMContentLoaded
