(() => {
  const selected = [];

  function $(s) { return document.querySelector(s); }
  function $$(s) { return [...document.querySelectorAll(s)]; }

  function showScreen(name) {
    $$('.screen').forEach(el => el.classList.toggle('active', el.id === `screen-${name}`));
    $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.screen === name));
    const title = $('#page-title');
    if (title) title.textContent = name === 'processing' ? 'AI Processing' : name === 'report' ? 'Inspection Report' : 'SmartMetrology AI';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setProcessing(text, label = 'Processing…') {
    const live = $('#ocr-live');
    const progress = $('#progress-label');
    const bar = $('#pipeline-progress');
    if (live) live.textContent = text;
    if (progress) progress.textContent = label;
    if (bar) bar.style.width = label.includes('complete') ? '100%' : '70%';
  }

  async function compressFile(file) {
    const bitmap = await createImageBitmap(file);
    const maxEdge = 640;
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext('2d', { alpha: false });
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return canvas.toDataURL('image/jpeg', 0.68);
  }

  function xhrJson(method, url, body, timeout = 90000) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      xhr.timeout = timeout;
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText || '{}'); } catch (_) {}
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error((data && (data.detail || data.message)) || `Inspection failed (${xhr.status})`));
      };
      xhr.onerror = () => reject(new Error('Network error while contacting inspection service.'));
      xhr.ontimeout = () => reject(new Error('Analysis timed out. Please retry once.'));
      xhr.send(JSON.stringify(body));
    });
  }

  function xhrBlob(method, url, body, timeout = 30000) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      xhr.timeout = timeout;
      xhr.responseType = 'blob';
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve(xhr.response) : reject(new Error(`PDF generation failed (${xhr.status})`));
      xhr.onerror = () => reject(new Error('PDF network error.'));
      xhr.ontimeout = () => reject(new Error('PDF generation timed out.'));
      xhr.send(JSON.stringify(body));
    });
  }

  async function downloadPdf(audit) {
    const blob = await xhrBlob('POST', '/api/export-pdf', {
      inspection_id: audit.inspection_id,
      commodity_name: audit.product_name || 'Packaged Commodity',
      overall_status: audit.overall_status || 'FAIL',
      compliance_score: Number(audit.compliance_score || 0),
      grade: audit.compliance_grade || '—',
      report: audit.audit_report || {}
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `SmartMetrology_${audit.inspection_id || 'Inspection'}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  function renderQuickReport(audit) {
    const status = String(audit.overall_status || 'FAIL').toUpperCase() === 'PASS' ? 'COMPLIANT' : 'NON-COMPLIANT';
    const reportStatus = $('#report-status');
    if (reportStatus) {
      reportStatus.textContent = status;
      reportStatus.className = `badge ${status === 'COMPLIANT' ? 'pass' : 'fail'}`;
    }
    const meta = $('#report-meta');
    if (meta) {
      const rows = [
        ['Inspection ID', audit.inspection_id || '—'],
        ['Product', audit.product_name || 'Packaged Commodity'],
        ['Screening score', `${Math.round(Number(audit.compliance_score || 0))}%`],
        ['Images analysed', `${audit.panels_count || selected.length} panel(s)`],
        ['Analysis mode', audit.analysis_mode || 'RapidOCR + Rule Engine']
      ];
      meta.innerHTML = rows.map(([k,v]) => `<div><span>${k}</span><b>${String(v).replace(/[&<>]/g, '')}</b></div>`).join('');
    }
    const violations = $('#report-violations');
    if (violations) {
      const items = Object.values(audit.audit_report || {}).filter(x => x && typeof x === 'object');
      violations.innerHTML = items.map(x => `<div class="report-violation"><b>${x.title || x.rule || 'Requirement'}</b><p>${x.status || ''} · ${x.detected_value || ''} · ${x.details || ''}</p></div>`).join('') || '<div class="review-record">Analysis completed.</div>';
    }
  }

  document.addEventListener('change', event => {
    if (event.target && event.target.id === 'image-input') {
      const target = Number(event.target.dataset.target || 0);
      const incoming = [...event.target.files].filter(f => f.type.startsWith('image/')).slice(0, 4);
      incoming.forEach((file, i) => { selected[Math.min(target + i, 3)] = file; });
      selected.splice(4);
    }
  }, true);

  document.addEventListener('drop', event => {
    const grid = event.target.closest && event.target.closest('#upload-grid');
    if (!grid) return;
    const incoming = [...event.dataTransfer.files].filter(f => f.type.startsWith('image/')).slice(0, 4);
    selected.splice(0, selected.length, ...incoming);
  }, true);

  document.addEventListener('click', async event => {
    const button = event.target.closest && event.target.closest('#start-inspection');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const files = selected.filter(Boolean);
    if (!files.length) {
      alert('Please upload at least one product image.');
      return;
    }

    button.disabled = true;
    showScreen('processing');
    setProcessing('Preparing and compressing product images…\nThen running OCR and Legal Metrology checks.', 'Preparing images…');

    try {
      const images = [];
      for (let i = 0; i < files.length; i++) {
        setProcessing(`Preparing image ${i + 1} of ${files.length}…`, 'Optimising images…');
        images.push({ name: files[i].name || `panel-${i + 1}.jpg`, data: await compressFile(files[i]) });
      }

      setProcessing('Images uploaded.\nRunning RapidOCR and deterministic compliance rules…', 'Analysing…');
      const audit = await xhrJson('POST', '/api/fast-audit-json', { images });
      window.__smartMetrologyLastAudit = audit;
      setProcessing('OCR and compliance analysis complete.\nPreparing PDF report…', '100% complete');
      renderQuickReport(audit);
      try { await downloadPdf(audit); } catch (pdfError) { console.error(pdfError); }
      showScreen('report');
    } catch (error) {
      setProcessing(`ERROR STATE\n${error.message}\n\nNo compliance decision was created.`, 'Processing failed');
    } finally {
      button.disabled = false;
    }
  }, true);
})();
