document.addEventListener('DOMContentLoaded',()=>{
  const head=document.head;
  if(head&&!document.querySelector('link[rel="manifest"]')){
    const manifest=document.createElement('link');manifest.rel='manifest';manifest.href='/static/manifest.webmanifest';head.append(manifest);
  }
  if('serviceWorker' in navigator){navigator.serviceWorker.register('/static/sw.js').catch(()=>{});}

  const top=document.querySelector('.top-actions');
  if(top){
    const status=document.createElement('span');
    status.className='v4-network-status';
    const render=()=>{status.textContent=navigator.onLine?'● ONLINE · SYNC READY':'● OFFLINE INSPECTION';status.classList.toggle('offline',!navigator.onLine);};
    render();window.addEventListener('online',render);window.addEventListener('offline',render);top.prepend(status);
  }

  const hero=document.querySelector('#screen-dashboard .hero-panel');
  if(hero){
    const capabilities=document.createElement('div');
    capabilities.className='v4-capability-ribbon';
    capabilities.innerHTML='<span>AI + OCR HYBRID</span><span>CV LAYOUT ANALYSIS</span><span>DYNAMIC RULE ENGINE</span><span>தமிழ் · हिंदी · తెలుగు · EN</span><span>OFFLINE READY</span>';
    hero.after(capabilities);
  }

  const scanner=document.querySelector('.scanner-panel');
  if(scanner){
    const note=document.createElement('div');
    note.className='v4-architecture-note';
    note.innerHTML='<b>SmartMetrology v4 pipeline</b><span>Image Processing AI → OCR + Language Detection → Product Category → Semantic/LLM Verification → Dynamic Rule Engine → Explainable Compliance Report</span>';
    scanner.prepend(note);
  }

  const processingTitle=document.querySelector('#screen-processing .processing-card h1');
  if(processingTitle)processingTitle.textContent='Running Hybrid AI Compliance Analysis';
  const processingCopy=document.querySelector('#screen-processing .processing-card p');
  if(processingCopy)processingCopy.textContent='Computer vision, OCR, regional-language normalization, product classification and deterministic rule validation are processed together.';

  const report=document.querySelector('.report-paper');
  if(report){
    const explain=document.createElement('div');
    explain.className='v4-explainability-seal';
    explain.innerHTML='<b>EXPLAINABLE AI RECORD</b><span>Each non-compliance must include a reason, applicable rule version and source evidence or absence-evidence.</span>';
    report.prepend(explain);
  }

  document.addEventListener('click',event=>{
    const btn=event.target.closest('#start-inspection');
    if(!btn||navigator.onLine)return;
    const files=[...(document.querySelector('#image-input')?.files||[])];
    const record={id:'OFF-'+Date.now(),createdAt:new Date().toISOString(),files:files.map(f=>({name:f.name,size:f.size,type:f.type})),status:'PENDING_SYNC'};
    const queue=JSON.parse(localStorage.getItem('sm-offline-queue')||'[]');queue.push(record);localStorage.setItem('sm-offline-queue',JSON.stringify(queue));
  },true);

  window.addEventListener('online',async()=>{
    const queue=JSON.parse(localStorage.getItem('sm-offline-queue')||'[]');
    if(!queue.length)return;
    for(const item of queue){
      try{await fetch('/api/v4/offline/queue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({record_id:item.id,payload:item})});}catch(_){return;}
    }
    localStorage.removeItem('sm-offline-queue');
  });
});
