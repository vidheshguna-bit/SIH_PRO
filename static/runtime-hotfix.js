(() => {
  const nativeFetch = window.fetch.bind(window);

  async function downloadPdf(audit) {
    const payload = {
      inspection_id: audit.inspection_id,
      commodity_name: audit.product_name || "Packaged Commodity",
      overall_status: audit.overall_status || "FAIL",
      compliance_score: Number(audit.compliance_score || 0),
      grade: audit.compliance_grade || "—",
      report: audit.audit_report || {}
    };
    const response = await nativeFetch("/api/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!response.ok) return;
    const blob = await response.blob();
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
    const url = typeof input === "string" ? input : input?.url || "";
    if (!(url === "/api/audit" || url.endsWith("/api/audit"))) return nativeFetch(input, init);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const response = await nativeFetch("/api/fast-audit", { ...init, signal: controller.signal });
      clearTimeout(timeout);
      if (!response.ok) {
        let message = `Inspection failed (${response.status})`;
        try {
          const body = await response.clone().json();
          message = body.detail || body.message || message;
        } catch (_) {}
        throw new Error(message);
      }
      const audit = await response.clone().json();
      window.__smartMetrologyLastAudit = audit;
      downloadPdf(audit).catch(() => {});
      return response;
    } catch (error) {
      clearTimeout(timeout);
      if (error?.name === "AbortError") throw new Error("Analysis timed out. Please retry once; the inspection server may be waking up.");
      throw error instanceof Error ? error : new Error("Inspection failed");
    }
  };
})();
