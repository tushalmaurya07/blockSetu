const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let demands=[],windows=[],blocks=[],history=[],lastPrediction=null;
const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const n=x=>Number(x||0).toLocaleString("en-IN",{maximumFractionDigits:1});
const money=x=>"₹"+Number(x||0).toLocaleString("en-IN",{maximumFractionDigits:0});
const pc=p=>({P1_CRITICAL:"p1",P2_HIGH:"p2",P3_MEDIUM:"p3",P4_LOW:"p4"}[p]||"p4");
async function api(path,opt){let r=await fetch(path,opt);if(!r.ok){let e=await r.json().catch(()=>({detail:r.statusText}));throw new Error(e.detail||"API error")}return r.json()}
function show(id){$$(".view").forEach(x=>x.classList.toggle("active",x.id===id));$$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.view===id));$("#title").textContent={dashboard:"Operations Dashboard",demands:"Unified Block Demands",planner:"AI + CP-SAT Planner",blocks:"Joint Possession Blocks",traffic:"Traffic-Aware Windows",history:"Execution History"}[id];scrollTo({top:0,behavior:"smooth"})}
$$(".nav").forEach(x=>x.onclick=()=>show(x.dataset.view));$$("[data-go]").forEach(x=>x.onclick=()=>show(x.dataset.go));
function table(h,rows){return `<div class="table-wrap"><table><thead><tr>${h.map(x=>`<th>${x}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`}
async function init(){
 try{
  const health=await api("/api/health");$("#health").textContent=`● ${health.ortools_cpsat?"XGBoost · SHAP · CP-SAT Ready":"XGBoost · SHAP Ready; install OR-Tools"}`;$("#ortools-status").textContent=health.ortools_cpsat?"✓ OR-Tools CP-SAT":"⚠ OR-Tools not installed";
  [demands,windows,blocks,history]=await Promise.all(["demands","windows","blocks","history"].map(x=>api("/api/"+x)));
  populateDemand();
  renderDashboard();renderDemands();renderBlocks();renderTraffic();renderHistory();
 }catch(e){$("#health").textContent="Backend not running";toast(e.message)}
}
function renderDashboard(){
 const c={P1_CRITICAL:0,P2_HIGH:0,P3_MEDIUM:0,P4_LOW:0};demands.forEach(x=>c[x.priority_tier]++);
 const approved=blocks.filter(x=>x.officer_approval_status==="APPROVED").length,saved=blocks.reduce((a,x)=>a+Number(x.saved_track_block_hours||0),0);
 $("#kpis").innerHTML=[["Demands",demands.length,"Complete dataset"],["P1 Critical",c.P1_CRITICAL,"Risk priority"],["Joint Blocks",blocks.length,`${approved} approved`],["Track Hours Saved",n(saved)+" h","Optimised blocks"]].map(x=>`<div class="card"><small>${x[0]}</small><b>${x[1]}</b><small>${x[2]}</small></div>`).join("");
 let max=Math.max(...Object.values(c));$("#priority").innerHTML=Object.entries(c).map(([k,v])=>`<div class="bar"><span>${k.replace("_"," ")}</span><div class="track"><div class="fill" style="width:${v/max*100}%;background:${k==="P1_CRITICAL"?"#d7463f":k==="P2_HIGH"?"#ed7b08":k==="P3_MEDIUM"?"#087bc1":"#9aa4b4"}"></div></div><b>${v}</b></div>`).join("");
 let pct=approved/blocks.length*100;$("#approval").innerHTML=`<div class="approval"><div class="donut" style="--p:${pct}%"><b>${Math.round(pct)}%</b></div><div><div>🟢 Approved <b>${approved}</b></div><div>🟠 Pending <b>${blocks.length-approved}</b></div></div></div>`;
}
function renderDemands(){
 let q=$("#search").value.toLowerCase(),data=demands.filter(x=>!q||[x.demand_id,x.section_code,x.work_description,x.department].join(" ").toLowerCase().includes(q)).slice(0,100);
 $("#demands-table").innerHTML=table(["ID","Source","Department","Section","Work","Priority","Score","Duration"],data.map(x=>`<tr><td><b>${esc(x.demand_id)}</b></td><td>${esc(x.source_system)}</td><td>${esc(x.department)}</td><td>${esc(x.section_code)}</td><td>${esc(x.work_description)}</td><td><span class="badge ${pc(x.priority_tier)}">${esc(x.priority_tier)}</span></td><td>${n(x.ai_priority_score)}</td><td>${n(x.duration_requested_min)} min</td></tr>`))
}
$("#search").oninput=renderDemands;
function renderBlocks(){ $("#blocks-table").innerHTML=table(["Block","Schedule","Departments","Jobs","Optimised","Saved","Approval","Rationale"],blocks.map(x=>`<tr><td>${esc(x.joint_block_id)}<br>${esc(x.section_code)}</td><td>${esc(x.scheduled_date)}<br>${esc(x.allocated_start_time)}–${esc(x.allocated_end_time)}</td><td>${esc(x.bundled_departments)}</td><td>${x.bundled_jobs_count}</td><td>${n(x.optimized_joint_block_hours)} h</td><td>${n(x.saved_track_block_hours)} h</td><td>${esc(x.officer_approval_status)}</td><td>${esc(x.ai_shap_explainable_rationale)}</td></tr>`))}
function renderTraffic(){ $("#traffic-table").innerHTML=table(["Window","Section","Date","Gap","Train Context","Penalty","Ideal","Power"],windows.map(x=>`<tr><td>${esc(x.window_id)}</td><td>${esc(x.section_code)}</td><td>${esc(x.window_date)}</td><td>${esc(x.window_start_time)}–${esc(x.window_end_time)}<br>${n(x.window_duration_min)} min</td><td>${esc(x.preceding_train_name)} → ${esc(x.following_train_name)}</td><td>${money(x.expected_train_delay_penalty_inr)}</td><td>${Number(x.is_ideal_joint_possession_window)?"YES":"NO"}</td><td>${x.ohe_power_cutoff_feasible?"YES":"NO"}</td></tr>`))}
function renderHistory(){ $("#history-table").innerHTML=table(["Log","Date","Dept","Section","Machine","Status","Idle","Delayed","Loss"],history.map(x=>`<tr><td>${esc(x.log_id)}</td><td>${esc(x.historical_date)}</td><td>${esc(x.department)}</td><td>${esc(x.section_code)}</td><td>${esc(x.machine_type_deployed)}</td><td>${esc(x.execution_status)}</td><td>${n(x.machine_idle_time_min)} min</td><td>${n(x.trains_delayed_count)}</td><td>${money(x.estimated_financial_loss_inr)}</td></tr>`))}
function populateDemand(){
 const el=$("#demand");
 if(!demands.length){
   el.innerHTML='<option value="">No demands loaded</option>';
   return;
 }
 el.innerHTML='<option value="">Select a maintenance demand...</option>'+
   demands.map(x=>`<option value="${esc(x.demand_id)}">${esc(x.demand_id)} · ${esc(x.section_code)} · ${esc(x.work_description)}</option>`).join("");
}
async function runPrediction(){
 const id=$("#demand").value;
 if(!id){toast("Please select a demand first.");return;}
 try{lastPrediction=await api("/api/predict/"+encodeURIComponent(id));renderPrediction(lastPrediction);toast("XGBoost + SHAP completed")}catch(e){toast(e.message)}
}
function renderPrediction(r){
 const s=r.model,top=s.shap, max=Math.max(...top.map(x=>Math.abs(x.shap)),.0001);
 $("#result").innerHTML=`<div class="result"><span class="badge ${pc(s.prediction)}">XGBOOST PREDICTION</span><h3>${esc(s.prediction)} · ${Math.round(s.confidence*100)}% confidence</h3><p class="mini">Probabilities: ${Object.entries(s.probabilities).map(([k,v])=>`${k}: ${Math.round(v*100)}%`).join(" · ")}</p></div><div class="result"><h3>SHAP explanation</h3><p class="mini">Largest feature contributions for this prediction.</p><div class="shap">${top.map(x=>`<div class="shaprow"><span>${esc(x.feature)}</span><div class="shaptrack"><div class="shapfill" style="width:${Math.abs(x.shap)/max*100}%"></div></div><b>${x.shap>=0?"+":""}${x.shap.toFixed(3)}</b></div>`).join("")}</div></div><div class="result"><h3>Next step</h3><p class="mini">Run CP-SAT to choose one compatible traffic window and bundle compatible maintenance jobs under duration constraints.</p></div>`;
}
$("#predict").onclick=runPrediction;
$("#optimize").onclick=async()=>{
 const id=$("#demand").value;
 if(!id){toast("Please select a demand first.");return;}
 try{let r=await api("/api/plan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({demand_id:id})});$("#result").innerHTML=`<div class="result"><span class="badge p3">CP-SAT ${esc(r.status)}</span><h3>Recommended Joint Block</h3><p><b>${esc(r.window.window_date)}</b> · ${esc(r.window.window_start_time)}–${esc(r.window.window_end_time)} · ${n(r.window.window_duration_min)} min</p><p class="mini">Delay penalty: ${money(r.window.expected_train_delay_penalty_inr)} · Ideal window: ${Number(r.window.is_ideal_joint_possession_window)?"YES":"NO"}</p></div><div class="result"><h3>Bundled jobs (${r.job_count})</h3>${r.selected_jobs.map(x=>`<p class="mini">• <b>${esc(x.demand_id)}</b> — ${esc(x.department)} — ${esc(x.work_description)} — ${n(x.duration_requested_min)} min</p>`).join("")}</div><div class="result"><h3>AI explanation</h3>${r.model_prediction.shap.slice(0,5).map(x=>`<p class="mini">${esc(x.feature)}: SHAP ${x.shap>=0?"+":""}${x.shap.toFixed(3)}</p>`).join("")}</div>`;toast("CP-SAT optimisation completed")}catch(e){toast(e.message)}
};
function toast(m){let t=$("#toast");t.textContent=m;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2300)}
init();
