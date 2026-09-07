(() => {
  const nativeFetch = window.fetch.bind(window);

  async function downloadPdfFromAudit(audit) {
    try {
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
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `SmartMetrology_${audit.inspection_id || "Inspection"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (_) {}
  }

  window.fetch = async (input, init = {}) => {
    let url = typeof input === "string" ? input : input?.url;
    const isAudit = url === "/api/audit";
    if (isAudit) {
      url = "/api/fast-audit";
      input = url;
      if (!init.signal) {
        const controller = new AbortController();
        init = { ...init, signal: controller.signal };
        setTimeout(() => controller.abort("Inspection timed out"), 45000);
      }
    }

    const response = await nativeFetch(input, init);
    if (isAudit && response.ok) {
      response.clone().json().then(audit => {
        window.__smartMetrologyLastAudit = audit;
        downloadPdfFromAudit(audit);
      }).catch(() => {});
    }
    return response;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const progress = document.querySelector("#progress-label");
    const ocr = document.querySelector("#ocr-live");
    const button = document.querySelector("#start-inspection");
    if (!button || !progress || !ocr) return;

    button.addEventListener("click", () => {
      let seconds = 0;
      progress.textContent = "FAST OCR · starting";
      ocr.textContent = "Uploading optimized product image…\nRunning single-pass OCR and compliance checks…";
      const timer = setInterval(() => {
        if (!document.querySelector("#screen-processing.active")) {
          clearInterval(timer);
          return;
        }
        seconds += 1;
        progress.textContent = `FAST OCR · ${seconds}s`;
        if (seconds === 4) ocr.textContent = "Reading package declarations…\nMRP · Net Quantity · Manufacturer · Dates · Consumer Care";
        if (seconds === 10) ocr.textContent = "Applying Legal Metrology rule checks…\nPreparing explainable result and PDF report.";
        if (seconds === 20) ocr.textContent = "Still processing this image on the free server…\nResult and PDF will appear automatically when complete.";
      }, 1000);
    }, { capture: true });
  });
})();
