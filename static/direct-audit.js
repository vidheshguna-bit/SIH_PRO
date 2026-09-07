(() => {
  const selected = [];
  function $(s){ return document.querySelector(s); }
  function $$(s){ return [...document.querySelectorAll(s)]; }
  function showScreen(name){
    $$('.screen').forEach(el => el.classList.toggle('active', el.id === `screen-${name}`));
    $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.screen === name));
    const t=$('#page-title'); if(t) t.textContent=name==='processing'?'AI Processing':name==='report'?'Inspection Report':'SmartMetrology AI';
    window.scrollTo({top:0,behavior:'smooth'});
  }
  function setProcessing(text,label='Processing…',pct=60){
    const live=$('#ocr-live'), progress=$('#progress-label'), bar=$('#pipeline-progress');
    if(live) live.textContent=text; if(progress) progress.textContent=label; if(bar) bar.style.width=`${pct}%`;
  }
  function xhrJson(method,url,body,timeout=30000){
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest(); xhr.open(method,url,true); xhr.timeout=timeout; xhr.setRequestHeader('Content-Type','application/json');
      xhr.onload=()=>{let d={};try{d=JSON.parse(xhr.responseText||'{}')}catch(_){ } if(xhr.status>=200&&xhr.status<300)resolve(d);else reject(new Error(d.detail||`Inspection failed (${xhr.status})`));};
      xhr.onerror=()=>reject(new Error('Network error while contacting inspection service.'));
      xhr.ontimeout=()=>reject(new Error('Compliance service timed out.'));
      xhr.send(JSON.stringify(body));
    });
  }
  function xhrBlob(method,url,body,timeout=30000){
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest(); xhr.open(method,url,true); xhr.timeout=timeout; xhr.responseType='blob'; xhr.setRequestHeader('Content-Type','application/json');
      xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(xhr.response):reject(new Error(`PDF generation failed (${xhr.status})`));
      xhr.onerror=()=>reject(new Error('PDF network error.')); xhr.ontimeout=()=>reject(new Error('PDF generation timed out.')); xhr.send(JSON.stringify(body));
    });
  }
  async function ocrFile(file,index,total){
    if(!window.Tesseract) throw new Error('Browser OCR engine failed to load. Refresh once and retry.');
    setProcessing(`Reading label text from image ${index+1} of ${total} on your device…\nThis avoids Render OCR memory crashes.`,`OCR ${index+1}/${total}…`,20+Math.round(index/total*55));
    const result=await Tesseract.recognize(file,'eng',{logger:m=>{
      if(m.status==='recognizing text'&&typeof m.progress==='number'){
        const pct=20+Math.round(((index+m.progress)/total)*55);
        setProcessing(`OCR image ${index+1}/${total}: ${Math.round(m.progress*100)}%\n${m.status}`,`OCR ${Math.round(m.progress*100)}%`,pct);
      }
    }});
    return result?.data?.text||'';
  }
  async function downloadPdf(audit){
    const blob=await xhrBlob('POST','/api/export-pdf',{inspection_id:audit.inspection_id,commodity_name:audit.product_name||'Packaged Commodity',overall_status:audit.overall_status||'REVIEW',compliance_score:Number(audit.compliance_score||0),grade:audit.compliance_grade||'—',report:audit.audit_report||{}});
    const u=URL.createObjectURL(blob),a=document.createElement('a'); a.href=u; a.download=`SmartMetrology_${audit.inspection_id||'Inspection'}.pdf`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(u),2000);
  }
  function renderQuickReport(audit){
    const status=String(audit.overall_status||'FAIL').toUpperCase()==='PASS'?'COMPLIANT':'NON-COMPLIANT';
    const rs=$('#report-status'); if(rs){rs.textContent=status;rs.className=`badge ${status==='COMPLIANT'?'pass':'fail'}`;}
    const meta=$('#report-meta'); if(meta){const rows=[['Inspection ID',audit.inspection_id||'—'],['Product',audit.product_name||'Packaged Commodity'],['Screening score',`${Math.round(Number(audit.compliance_score||0))}%`],['Images analysed',`${audit.panels_count||selected.length} panel(s)`],['Analysis mode','Browser OCR + Rule Engine']]; meta.innerHTML=rows.map(([k,v])=>`<div><span>${k}</span><b>${String(v).replace(/[&<>]/g,'')}</b></div>`).join('');}
    const violations=$('#report-violations'); if(violations){const items=Object.values(audit.audit_report||{}).filter(x=>x&&typeof x==='object'); violations.innerHTML=items.map(x=>`<div class="report-violation"><b>${x.title||x.rule||'Requirement'}</b><p>${x.status||''} · ${x.detected_value||''} · ${x.details||''}</p></div>`).join('')||'<div class="review-record">Analysis completed.</div>';}
  }
  document.addEventListener('change',e=>{if(e.target?.id==='image-input'){const target=Number(e.target.dataset.target||0);const incoming=[...e.target.files].filter(f=>f.type.startsWith('image/')).slice(0,4);incoming.forEach((f,i)=>selected[Math.min(target+i,3)]=f);selected.splice(4);}},true);
  document.addEventListener('drop',e=>{const grid=e.target.closest&&e.target.closest('#upload-grid');if(!grid)return;const incoming=[...e.dataTransfer.files].filter(f=>f.type.startsWith('image/')).slice(0,4);selected.splice(0,selected.length,...incoming);},true);
  document.addEventListener('click',async e=>{
    const button=e.target.closest&&e.target.closest('#start-inspection'); if(!button)return; e.preventDefault(); e.stopImmediatePropagation();
    const files=selected.filter(Boolean); if(!files.length){alert('Please upload at least one product image.');return;}
    button.disabled=true; showScreen('processing');
    try{
      const texts=[]; for(let i=0;i<files.length;i++) texts.push(await ocrFile(files[i],i,files.length));
      if(!texts.join('').trim()) throw new Error('No readable label text detected. Try a clearer back-label image.');
      setProcessing('OCR complete on your laptop.\nSending only extracted text for Legal Metrology rule validation…','Validating rules…',88);
      const audit=await xhrJson('POST','/api/text-audit',{texts,filenames:files.map(f=>f.name||'product.jpg')},30000);
      window.__smartMetrologyLastAudit=audit; setProcessing('Compliance analysis complete.\nPreparing inspection report…','100% complete',100); renderQuickReport(audit);
      try{await downloadPdf(audit);}catch(err){console.error(err);} showScreen('report');
    }catch(error){setProcessing(`ERROR STATE\n${error.message}\n\nNo compliance decision was created.`,'Processing failed',100);}
    finally{button.disabled=false;}
  },true);
})();
