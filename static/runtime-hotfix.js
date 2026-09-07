(() => {
  const nativeFetch = window.fetch.bind(window);

  async function downloadPdfFromAudit(audit) {
    const payload = {
      inspection_id: audit.inspection_id,
      commodity_name: audit.product_name || "Packaged Commodity",
      overall_status: audit.overall_status || "FAIL",
      compliance_score: Number(audit.compliance_score || 0),
      grade: audit.compliance_grade || "—",
      report: audit.audit_report || {}
    };
    const res = await nativeFetch("/api/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`PDF generation failed (${res.status})`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `SmartMetrology_${audit.inspection_id || "Inspection"}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  window.fetch = async (input, init = {}) => {
    const originalUrl = typeof input === "string" ? input : input?.url;
    const isAudit = originalUrl === "/api/audit" || originalUrl?.endsWith("/api/audit");
    if (!isAudit) return nativeFetch(input, init);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60000);
    try {
      const requestInit = { ...init, signal: controller.signal };
      const response = await nativeFetch("/api/fast-audit", requestInit);
      clearTimeout(timeout);

      if (!response.ok) {
        let message = `Inspection service returned ${response.status}`;
        try {
          const data = await response.clone().json();
          message = data.detail || data.message || message;
        } catch (_) {}
        throw new Error(message);
      }

      const audit = await response.clone().json();
      window.__smartMetrologyLastAudit = audit;
      downloadPdfFromAudit(audit).catch(console.error);
      return response;
    } catch (err) {
      clearTimeout(timeout);
      if (err?.name === "AbortError") throw new Error("Analysis timed out after 60 seconds. Please use a clearer or smaller image.");
      if (err instanceof Error) throw err;
      throw new Error(String(err || "Inspection failed"));
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    const progress = document.querySelector("#progress-label");
    const ocr = document.querySelector("#ocr-live");
    const button = document.querySelector("#start-inspection");
    if (!button || !progress || !ocr) return;

    button.addEventListener("click", () => {
      let seconds = 0;
      progress.textContent = "FAST OCR · starting";
      ocr.textContent = "Uploading product images…\nRunning OCR and Legal Metrology checks…";
      const timer = setInterval(() => {
        if (!document.querySelector("#screen-processing.active")) {
          clearInterval(timer);
          return;
        }
        seconds += 1;
        progress.textContent = `FAST OCR · ${seconds}s`;
        if (seconds === 3) ocr.textContent = "Reading package declarations…\nMRP · Net Quantity · Manufacturer · Dates · Consumer Care";
        if (seconds === 8) ocr.textContent = "Applying Legal Metrology rules…\nPreparing compliance result and PDF.";
        if (seconds === 20) ocr.textContent = "Processing on Render free compute…\nPlease keep this tab open.";
        if (seconds >= 60) {
          clearInterval(timer);
          progress.textContent = "Processing timeout";
        }
      }, 1000);
    }, { capture: true });
  });
})();
