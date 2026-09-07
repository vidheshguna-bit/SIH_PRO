(() => {
  const previousFetch = window.fetch.bind(window);

  async function fileToOptimizedDataUrl(file) {
    const bitmap = await createImageBitmap(file);
    const maxEdge = 720;
    const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d', { alpha: false });
    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();
    return canvas.toDataURL('image/jpeg', 0.72);
  }

  async function downloadPdf(audit) {
    try {
      const response = await previousFetch('/api/export-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          inspection_id: audit.inspection_id,
          commodity_name: audit.product_name || 'Packaged Commodity',
          overall_status: audit.overall_status || 'FAIL',
          compliance_score: Number(audit.compliance_score || 0),
          grade: audit.compliance_grade || '—',
          report: audit.audit_report || {}
        })
      });
      if (!response.ok) return;
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `SmartMetrology_${audit.inspection_id || 'Inspection'}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (_) {}
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url;
    const isAudit = url === '/api/audit' || url?.endsWith('/api/audit');
    if (!isAudit || !(init.body instanceof FormData)) return previousFetch(input, init);

    const files = init.body.getAll('files').filter(x => x instanceof File);
    if (!files.length) throw new Error('Please upload at least one product image.');

    const images = [];
    for (const file of files.slice(0, 4)) {
      images.push({ name: file.name || 'product.jpg', data: await fileToOptimizedDataUrl(file) });
    }

    let lastError = null;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 70000);
        const response = await previousFetch('/api/fast-audit-json', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ images }),
          signal: controller.signal
        });
        clearTimeout(timeout);
        if (!response.ok) {
          let message = `Inspection failed (${response.status})`;
          try {
            const data = await response.clone().json();
            message = data.detail || message;
          } catch (_) {}
          throw new Error(message);
        }
        const audit = await response.clone().json();
        window.__smartMetrologyLastAudit = audit;
        downloadPdf(audit);
        return response;
      } catch (err) {
        lastError = err;
        if (attempt === 1) await new Promise(r => setTimeout(r, 1800));
      }
    }

    if (lastError?.name === 'AbortError') throw new Error('Analysis timed out. Please retry once.');
    throw lastError instanceof Error ? lastError : new Error('Inspection failed.');
  };
})();
