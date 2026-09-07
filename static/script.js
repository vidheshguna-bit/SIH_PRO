/**
 * LM Audit · SIH26034
 * Advanced Multi-Panel, Bulk Auditing & Analytics Controller
 */

document.addEventListener("DOMContentLoaded", () => {
    // ── Application State ──────────────────────
    let activeView          = "inspector"; // "inspector" | "analytics"
    let auditMode           = "single";    // "single" | "bulk"
    let currentAuditData    = null;
    let activePanelIndex    = 0;
    let currentImage        = null;
    let zoomLevel           = 1.0;
    let showOverlays        = true;
    let hoveredToken        = null;
    let highlightedRuleKey  = null;
    let analyticsDataCache  = null;
    let ledgerFilterStatus  = "ALL";
    let ledgerSearchQuery   = "";
    let loaderStageTimer    = null;

    // ── DOM Elements ───────────────────────────
    const tabInspector      = document.getElementById("tab-btn-inspector");
    const tabAnalytics      = document.getElementById("tab-btn-analytics");
    const viewInspector     = document.getElementById("view-inspector");
    const viewAnalytics     = document.getElementById("view-analytics");
    const subBarInspector   = document.getElementById("sub-bar-inspector");
    const analyticsBadge    = document.getElementById("nav-analytics-badge");

    const btnModeSingle     = document.getElementById("btn-mode-single");
    const btnModeBulk       = document.getElementById("btn-mode-bulk");
    const uploadBtnText     = document.getElementById("upload-btn-text");
    const imageUpload       = document.getElementById("image-upload");

    const canvas            = document.getElementById("inspection-canvas");
    const ctx               = canvas.getContext("2d");
    const canvasContainer   = document.getElementById("canvas-container");
    const canvasWrapper     = document.getElementById("canvas-wrapper");
    const dropZone          = document.getElementById("drop-placeholder");
    const dropTitle         = document.getElementById("drop-zone-title");
    const dropSub           = document.getElementById("drop-zone-sub");
    const loader            = document.getElementById("processing-loader");
    const loaderStatusText  = document.getElementById("loader-status-text");
    const tooltip           = document.getElementById("canvas-tooltip");
    const panelCounter      = document.getElementById("panel-counter");
    const activePanelTag    = document.getElementById("active-panel-tag");
    const metaTag           = document.getElementById("inspection-meta-tag");
    const productNamePill   = document.getElementById("product-name-pill");
    const auditContent      = document.getElementById("audit-content");
    const auditPanelTitle   = document.getElementById("audit-panel-title");
    const panelThumbsStrip  = document.getElementById("panel-thumbnails-strip");

    const toggleOverlay     = document.getElementById("toggle-overlay");
    const btnZoomIn         = document.getElementById("btn-zoom-in");
    const btnZoomOut        = document.getElementById("btn-zoom-out");
    const btnZoomReset      = document.getElementById("btn-zoom-reset");
    const btnExportPdf      = document.getElementById("btn-export-pdf");
    const btnRawJson        = document.getElementById("btn-raw-json");
    const jsonModal         = document.getElementById("json-modal");
    const btnCloseModal     = document.getElementById("btn-close-modal");
    const btnCopyJson       = document.getElementById("btn-copy-json");
    const jsonDisplay       = document.querySelector("#json-display code");

    // Analytics DOM
    const kpiTotalAudited   = document.getElementById("kpi-total-audited");
    const kpiPassRate       = document.getElementById("kpi-pass-rate");
    const kpiPassCount      = document.getElementById("kpi-pass-count");
    const kpiWarnRate       = document.getElementById("kpi-warn-rate");
    const kpiWarnCount      = document.getElementById("kpi-warn-count");
    const kpiFailRate       = document.getElementById("kpi-fail-rate");
    const kpiFailCount      = document.getElementById("kpi-fail-count");
    const kpiAvgScore       = document.getElementById("kpi-avg-score");
    const defectBarsContainer = document.getElementById("defect-bars-container");
    const ledgerTableBody   = document.getElementById("ledger-table-body");
    const ledgerProductCount = document.getElementById("ledger-product-count");
    const ledgerSearchInput = document.getElementById("ledger-search-input");
    const btnLoadDemoBatch  = document.getElementById("btn-load-demo-batch");
    const btnExportCsv      = document.getElementById("btn-export-csv");

    // ── Primary View Tab Switcher ───────────────
    tabInspector.addEventListener("click", () => switchView("inspector"));
    tabAnalytics.addEventListener("click", () => switchView("analytics"));

    function switchView(viewName) {
        activeView = viewName;
        tabInspector.classList.toggle("active", viewName === "inspector");
        tabAnalytics.classList.toggle("active", viewName === "analytics");
        viewInspector.classList.toggle("active", viewName === "inspector");
        viewAnalytics.classList.toggle("active", viewName === "analytics");
        subBarInspector.style.display = viewName === "inspector" ? "flex" : "none";

        if (viewName === "analytics") {
            loadAnalyticsData();
        } else {
            if (currentImage) redraw();
        }
    }

    // ── Audit Mode Selector ────────────────────
    btnModeSingle.addEventListener("click", () => setAuditMode("single"));
    btnModeBulk.addEventListener("click", () => setAuditMode("bulk"));

    function setAuditMode(mode) {
        auditMode = mode;
        btnModeSingle.classList.toggle("active", mode === "single");
        btnModeBulk.classList.toggle("active", mode === "bulk");

        if (mode === "single") {
            uploadBtnText.textContent = "Upload Product Panel(s)";
            dropTitle.textContent = "Drop Product Panel Photos Here";
            dropSub.textContent = "Upload multiple panels (Front, Back, Nutrition) for a single packaged commodity";
        } else {
            uploadBtnText.textContent = "Upload Bulk Products (Batch)";
            dropTitle.textContent = "Drop Multiple Products for Batch Audit";
            dropSub.textContent = "Upload 5, 10 or 20+ distinct product packaging photos for concurrent compliance auditing";
        }
    }

    // ── Sample Benchmarks ──────────────────────
    document.querySelectorAll(".chip[data-sample]").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".chip[data-sample]").forEach(chip => chip.classList.toggle("active", chip === btn));
            switchView("inspector");
            setAuditMode("single");
            loadSampleAudit(btn.dataset.sample);
        });
    });

    // ── File Upload Listener ───────────────────
    imageUpload.addEventListener("change", e => {
        if (e.target.files?.length) {
            document.querySelectorAll(".chip[data-sample]").forEach(chip => chip.classList.remove("active"));
            handleUploadedFiles(e.target.files);
            imageUpload.value = "";
        }
    });

    dropZone.addEventListener("click", () => imageUpload.click());
    dropZone.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            imageUpload.click();
        }
    });

    // ── Drag & Drop ────────────────────────────
    canvasContainer.addEventListener("dragover", e => {
        e.preventDefault();
        canvasContainer.classList.add("drag-hover");
    });
    canvasContainer.addEventListener("dragleave", () => canvasContainer.classList.remove("drag-hover"));
    canvasContainer.addEventListener("drop", e => {
        e.preventDefault();
        canvasContainer.classList.remove("drag-hover");
        if (e.dataTransfer.files?.length) {
            handleUploadedFiles(e.dataTransfer.files);
        }
    });

    function handleUploadedFiles(fileList) {
        if (auditMode === "single") {
            uploadSingleProductPanels(fileList);
        } else {
            uploadBulkProducts(fileList);
        }
    }

    // ── Zoom & Canvas Controls ─────────────────
    btnZoomIn.addEventListener("click", () => setZoom(zoomLevel * 1.3));
    btnZoomOut.addEventListener("click", () => setZoom(zoomLevel / 1.3));
    btnZoomReset.addEventListener("click", () => fitToView());
    toggleOverlay.addEventListener("change", e => {
        showOverlays = e.target.checked;
        redraw();
    });

    // ── JSON Modal ─────────────────────────────
    btnRawJson.addEventListener("click", () => {
        if (!currentAuditData) return;
        jsonDisplay.textContent = JSON.stringify(currentAuditData, null, 2);
        jsonModal.classList.remove("hidden");
    });
    btnCloseModal.addEventListener("click", () => jsonModal.classList.add("hidden"));
    jsonModal.addEventListener("click", e => { if (e.target === jsonModal) jsonModal.classList.add("hidden"); });
    btnCopyJson.addEventListener("click", () => {
        navigator.clipboard.writeText(JSON.stringify(currentAuditData, null, 2));
        btnCopyJson.textContent = "Copied ✓";
        setTimeout(() => btnCopyJson.textContent = "Copy JSON", 2000);
    });

    // ── PDF Export ─────────────────────────────
    btnExportPdf.addEventListener("click", exportPdfCertificate);

    // ── Analytics Actions ──────────────────────
    btnLoadDemoBatch.addEventListener("click", async () => {
        btnLoadDemoBatch.disabled = true;
        btnLoadDemoBatch.textContent = "Loading 12 Products…";
        try {
            const res = await fetch("/api/analytics/demo", { method: "POST" });
            const data = await res.json();
            renderAnalyticsDashboard(data);
        } catch (err) {
            alert("Demo batch load failed: " + err.message);
        } finally {
            btnLoadDemoBatch.disabled = false;
            btnLoadDemoBatch.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Load Demo Batch (12 Products)`;
        }
    });

    btnExportCsv.addEventListener("click", () => {
        window.location.href = "/api/analytics/export-csv";
    });

    ledgerSearchInput.addEventListener("input", e => {
        ledgerSearchQuery = e.target.value.toLowerCase().trim();
        filterAndRenderLedger();
    });

    document.querySelectorAll(".filter-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            ledgerFilterStatus = pill.dataset.filter;
            filterAndRenderLedger();
        });
    });

    // ══════════════════════════════════════════
    // API AUDIT CALLS
    // ══════════════════════════════════════════

    async function loadSampleAudit(sampleName) {
        showLoader(true, "Auditing Sample Commodity…");
        try {
            const res = await fetch(`/api/sample/${sampleName}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            renderSingleProductAudit(data);
            refreshAnalyticsBadge();
        } catch (err) {
            alert("Failed to load sample: " + err.message);
        } finally {
            showLoader(false);
        }
    }

    async function uploadSingleProductPanels(fileList) {
        showLoader(true, `Auditing ${fileList.length} Packaging Panel(s)…`);
        const fd = new FormData();
        for (const f of fileList) fd.append("files", f);

        try {
            const res = await fetch("/api/audit", { method: "POST", body: fd });
            if (!res.ok) {
                const d = await res.json();
                throw new Error(d.detail || "Upload audit error");
            }
            const data = await res.json();
            renderSingleProductAudit(data);
            refreshAnalyticsBadge();
        } catch (err) {
            alert("Audit failed: " + err.message);
        } finally {
            showLoader(false);
        }
    }

    async function uploadBulkProducts(fileList) {
        showLoader(true, `Executing Bulk Audit on ${fileList.length} Products…`);
        const fd = new FormData();
        for (const f of fileList) fd.append("files", f);

        try {
            const res = await fetch("/api/audit/bulk", { method: "POST", body: fd });
            if (!res.ok) {
                const d = await res.json();
                throw new Error(d.detail || "Bulk audit error");
            }
            const batchData = await res.json();
            renderBulkBatchResults(batchData);
            refreshAnalyticsBadge();
        } catch (err) {
            alert("Bulk audit failed: " + err.message);
        } finally {
            showLoader(false);
        }
    }

    async function inspectProductById(inspectionId) {
        showLoader(true, "Loading Product Scan into Inspector…");
        switchView("inspector");
        setAuditMode("single");
        try {
            const res = await fetch(`/api/audit/product/${inspectionId}`);
            if (!res.ok) throw new Error("Could not find product audit record");
            const data = await res.json();
            renderSingleProductAudit(data);
        } catch (err) {
            alert(err.message);
        } finally {
            showLoader(false);
        }
    }

    async function exportPdfCertificate() {
        if (!currentAuditData) return;
        btnExportPdf.disabled = true;
        btnExportPdf.innerHTML = "Generating…";
        try {
            const payload = {
                inspection_id:    currentAuditData.inspection_id,
                commodity_name:   currentAuditData.product_name || "Packaged Commodity",
                overall_status:   currentAuditData.overall_status,
                compliance_score: currentAuditData.compliance_score,
                grade:            currentAuditData.compliance_grade,
                report:           currentAuditData.audit_report
            };
            const res = await fetch("/api/export-pdf", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error("PDF generation failed");
            const blob = await res.blob();
            const a = Object.assign(document.createElement("a"), {
                href:     URL.createObjectURL(blob),
                download: `Legal_Metrology_Inspection_${currentAuditData.inspection_id}.pdf`
            });
            document.body.appendChild(a); a.click(); a.remove();
        } catch (err) {
            alert("PDF export failed: " + err.message);
        } finally {
            btnExportPdf.disabled = false;
            btnExportPdf.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> Export PDF`;
        }
    }

    // ══════════════════════════════════════════
    // RENDERING: SINGLE PRODUCT (MULTI-PANEL)
    // ══════════════════════════════════════════

    function renderSingleProductAudit(data) {
        currentAuditData    = data;
        activePanelIndex    = 0;
        highlightedRuleKey  = null;

        btnExportPdf.disabled = false;
        btnRawJson.disabled   = false;
        metaTag.textContent   = `Ref: ${data.inspection_id}`;

        if (data.product_name) {
            productNamePill.textContent = `Product: ${data.product_name}`;
            productNamePill.classList.remove("hidden");
        } else {
            productNamePill.classList.add("hidden");
        }

        auditPanelTitle.textContent = "Statutory Audit Report";

        const panels = data.panels || [];
        panelCounter.textContent = `${panels.length} Panel${panels.length !== 1 ? 's' : ''} Scanned`;

        // Render Multi-Panel Thumbnail Gallery Strip
        renderPanelThumbnails(panels);

        // Render Right Side Statutory Rule Cards
        renderStatutoryCards(data);

        // Load active panel image onto canvas
        if (panels.length > 0) {
            loadPanelImage(0);
        }
    }

    function renderPanelThumbnails(panels) {
        if (!panels || panels.length <= 1) {
            panelThumbsStrip.classList.add("hidden");
            activePanelTag.classList.add("hidden");
            return;
        }

        panelThumbsStrip.classList.remove("hidden");
        activePanelTag.classList.remove("hidden");
        panelThumbsStrip.innerHTML = "";

        panels.forEach((p, idx) => {
            const card = document.createElement("div");
            card.className = `thumb-card ${idx === 0 ? 'active' : ''}`;
            card.id = `thumb-panel-${idx}`;

            const labelName = idx === 0 ? "Front Panel" : (idx === 1 ? "Back Panel" : `Side Panel ${idx - 1}`);

            card.innerHTML = `
                <img src="${p.image_b64}" class="thumb-preview" alt="Panel ${idx + 1}">
                <div class="thumb-info">
                    <span class="thumb-title">${labelName}</span>
                    <span class="thumb-meta">${p.token_count || 0} tokens · ${p.dimensions?.width}x${p.dimensions?.height}</span>
                </div>
            `;

            card.addEventListener("click", () => switchActivePanel(idx, labelName));
            panelThumbsStrip.appendChild(card);
        });

        activePanelTag.textContent = "Panel 1 (Front)";
    }

    function switchActivePanel(idx, labelName) {
        activePanelIndex = idx;
        document.querySelectorAll(".thumb-card").forEach((c, i) => {
            c.classList.toggle("active", i === idx);
        });
        activePanelTag.textContent = labelName || `Panel ${idx + 1}`;
        loadPanelImage(idx);
    }

    function loadPanelImage(idx) {
        const panels = currentAuditData?.panels || [];
        const panel = panels[idx];
        if (!panel) return;

        const img = new Image();
        img.onload = () => {
            currentImage = img;
            dropZone.classList.add("hidden");
            canvasWrapper.classList.remove("hidden");
            fitToView();
        };
        img.src = panel.image_b64;
    }

    function renderStatutoryCards(data) {
        const st    = data.overall_status;
        const score = data.compliance_score;
        const rep   = data.audit_report || {};

        const pillClass = st === "PASS" ? "pill-pass" : (st === "WARNING" ? "pill-warn" : "pill-fail");
        const barColor  = st === "PASS" ? "var(--pass)" : (st === "WARNING" ? "var(--warn)" : "var(--fail)");

        let html = `
        <div class="summary-card">
            <div class="summary-top">
                <div class="verdict-pill ${pillClass}">
                    <div class="verdict-dot"></div>
                    VERDICT: ${st}
                </div>
                <div class="score-block">
                    <div class="score-num">${score}<span style="font-size:13px;color:var(--txt-muted);">%</span></div>
                    <div class="score-bar-wrap">
                        <div class="score-label">Compliance</div>
                        <div class="score-bar-bg">
                            <div class="score-bar-fill" style="width:${score}%;background:${barColor};"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="summary-stats">
                <div class="stat-cell">
                    <div class="stat-val" style="color:var(--pass)">${data.passed_rules_count}</div>
                    <div class="stat-lbl">Compliant</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-val" style="color:var(--warn)">${data.warnings_count}</div>
                    <div class="stat-lbl">Warnings</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-val" style="color:var(--fail)">${data.violations_count}</div>
                    <div class="stat-lbl">Violations</div>
                </div>
            </div>
        </div>`;

        if (data.violations_summary?.length) {
            html += `
            <div class="violations-box">
                <div class="violations-box-title">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    ${data.violations_summary.length} Statutory Action Item${data.violations_summary.length !== 1 ? "s" : ""}
                </div>
                <ul class="violations-list">
                    ${data.violations_summary.map(v => `<li><b>${v.rule}:</b> ${v.details}</li>`).join("")}
                </ul>
            </div>`;
        }

        const RULES = [
            { key: "rule_6_1_e_mrp",              label: "MRP & Mandatory Tax Declaration" },
            { key: "rule_6_1_c_net_quantity",      label: "Net Quantity & Metric SI Unit (Rule 12)" },
            { key: "rule_6_1_11_unit_sale_price",  label: "Unit Sale Price (USP) & Math Check" },
            { key: "rule_6_1_d_mfg_date",          label: "Month & Year of Packing / Mfg" },
            { key: "rule_6_1_da_consumer_grievance",label: "Consumer Grievance Contact (Helpline/Email)" },
            { key: "rule_6_1_a_manufacturer",      label: "Manufacturer / Packer Identity & Address" },
            { key: "rule_6_1_b_commodity_name",    label: "Common Generic Commodity Name" },
        ];

        html += `<div style="display:flex;flex-direction:column;gap:8px;">`;
        for (const r of RULES) {
            const rd = rep[r.key];
            if (!rd) continue;
            const s = rd.status || "FAIL";
            const isOk = s === "COMPLIANT";
            const isWarn = s === "WARNING";
            const chipC   = isOk ? "chip-s-pass" : (isWarn ? "chip-s-warn" : "chip-s-fail");
            const detailC = isOk ? "detail-pass" : (isWarn ? "detail-warn" : "detail-fail");
            const bbox    = Array.isArray(rd.bbox_reference) && rd.bbox_reference.length === 4;

            html += `
            <div class="rule-card" id="card-${r.key}" data-rule="${r.key}">
                <div class="rule-card-header">
                    <div class="rule-tag-row">
                        <span class="rule-code">${rd.rule}</span>
                        <span class="rule-name">${r.label}</span>
                    </div>
                    <span class="status-chip ${chipC}">${s}</span>
                </div>
                <div class="rule-card-body">
                    <div class="detected-row">
                        <span class="det-label">Detected Value</span>
                        <span class="det-value">${rd.detected_value || "—"}</span>
                    </div>
                    <div class="clause-quote">${rd.legal_clause || ""}</div>
                    <div class="detail-box ${detailC}">${rd.details || ""}</div>
                    ${bbox ? `
                        <button class="focus-btn" data-bbox="${rd.bbox_reference.join(",")}">
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                            Focus Bounding Box
                        </button>` : ""}
                </div>
            </div>`;
        }
        html += `</div>`;

        auditContent.innerHTML = html;
        auditContent.classList.remove("results-enter");
        requestAnimationFrame(() => auditContent.classList.add("results-enter"));

        document.querySelectorAll(".focus-btn").forEach(btn => {
            btn.addEventListener("click", e => {
                e.stopPropagation();
                zoomToBBox(btn.dataset.bbox.split(",").map(Number));
            });
        });

        document.querySelectorAll(".rule-card").forEach(card => {
            card.addEventListener("click", () => highlightRule(card.dataset.rule));
        });
    }

    // ══════════════════════════════════════════
    // RENDERING: BULK BATCH RESULTS
    // ══════════════════════════════════════════

    function renderBulkBatchResults(batchData) {
        btnExportPdf.disabled = true;
        btnRawJson.disabled = false;
        currentAuditData = batchData;
        metaTag.textContent = `Batch: ${batchData.batch_id}`;
        panelCounter.textContent = `${batchData.total_processed} Products Processed`;
        productNamePill.textContent = `Batch Audit (${batchData.pass_rate}% Pass Rate)`;
        productNamePill.classList.remove("hidden");
        panelThumbsStrip.classList.add("hidden");
        activePanelTag.classList.add("hidden");

        auditPanelTitle.textContent = `Batch Summary (${batchData.total_processed} Products)`;

        let html = `
        <div class="summary-card">
            <div class="summary-top">
                <div class="verdict-pill pill-pass">
                    <div class="verdict-dot"></div>
                    BATCH COMPLETE: ${batchData.pass_rate}%
                </div>
                <div class="score-block">
                    <div class="score-num">${batchData.total_processed}</div>
                    <div class="score-bar-wrap">
                        <div class="score-label">Products</div>
                    </div>
                </div>
            </div>
            <div class="summary-stats">
                <div class="stat-cell">
                    <div class="stat-val text-pass">${batchData.pass_count}</div>
                    <div class="stat-lbl">Passed</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-val text-warn">${batchData.warnings_count}</div>
                    <div class="stat-lbl">Warnings</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-val text-fail">${batchData.violations_count}</div>
                    <div class="stat-lbl">Violations</div>
                </div>
            </div>
        </div>
        <div style="font-size:12px;color:var(--txt-muted);padding:4px 2px;">
            Click any product below to inspect its label and bounding boxes on the canvas:
        </div>
        <div class="batch-results-list">`;

        (batchData.products || []).forEach(p => {
            const st = p.overall_status;
            const chipClass = st === "PASS" ? "chip-s-pass" : (st === "WARNING" ? "chip-s-warn" : "chip-s-fail");
            html += `
            <div class="batch-item-card" data-id="${p.inspection_id}">
                <div class="batch-item-left">
                    <img src="${p.thumbnail}" class="batch-item-thumb" alt="${p.product_name}">
                    <div class="batch-item-info">
                        <span class="batch-item-name">${p.product_name}</span>
                        <span class="batch-item-sub">${p.inspection_id} · Score: ${p.compliance_score}%</span>
                    </div>
                </div>
                <span class="status-chip ${chipClass}">${st}</span>
            </div>`;
        });

        html += `</div>`;
        auditContent.innerHTML = html;

        document.querySelectorAll(".batch-item-card").forEach(card => {
            card.addEventListener("click", () => {
                inspectProductById(card.dataset.id);
            });
        });

        // If products exist, load the first one on the canvas
        if (batchData.products?.length > 0) {
            inspectProductById(batchData.products[0].inspection_id);
        }
    }

    // ══════════════════════════════════════════
    // RENDERING: ANALYTICS & INSIGHTS DASHBOARD
    // ══════════════════════════════════════════

    async function loadAnalyticsData() {
        try {
            const res = await fetch("/api/analytics");
            if (!res.ok) throw new Error("Could not fetch analytics data");
            const data = await res.json();
            renderAnalyticsDashboard(data);
        } catch (err) {
            console.error("Analytics fetch error:", err);
        }
    }

    async function refreshAnalyticsBadge() {
        try {
            const res = await fetch("/api/analytics");
            if (res.ok) {
                const data = await res.json();
                analyticsBadge.textContent = data.total_audited || 0;
            }
        } catch (e) {}
    }

    function renderAnalyticsDashboard(data) {
        analyticsDataCache = data;
        analyticsBadge.textContent = data.total_audited || 0;

        // Populate KPIs
        kpiTotalAudited.textContent = data.total_audited;
        kpiPassRate.textContent     = `${data.pass_rate}%`;
        kpiPassCount.textContent    = `${data.pass_count} items compliant`;
        kpiWarnRate.textContent     = `${data.warn_rate}%`;
        kpiWarnCount.textContent    = `${data.warnings_count} items with warnings`;
        kpiFailRate.textContent     = `${data.fail_rate}%`;
        kpiFailCount.textContent    = `${data.violations_count} items with violations`;
        kpiAvgScore.textContent     = `${data.avg_compliance_score}%`;

        // Populate Defect Frequency Bars
        renderDefectFrequencyBars(data.defect_frequency || {}, data.total_audited);

        // Populate Ledger Table
        filterAndRenderLedger();
    }

    function renderDefectFrequencyBars(defects, total) {
        const DEFECT_LABELS = [
            { key: "rule_6_1_e",        label: "Rule 6(1)(e): Missing MRP or 'Inclusive of all taxes'", color: "var(--fail)" },
            { key: "rule_12_units",      label: "Rule 12(1): Prohibited Metric Symbols ('gms', 'ltr')",   color: "var(--warn)" },
            { key: "rule_6_1_11_usp",    label: "Rule 6(1)(11): Unit Sale Price (USP) Math Mismatch",     color: "var(--fail)" },
            { key: "rule_6_1_da_care",   label: "Rule 6(1)(da): Missing Grievance Helpline / Email",      color: "var(--fail)" },
            { key: "rule_6_1_d_date",    label: "Rule 6(1)(d): Omitted Manufacturing / Packing Date",     color: "var(--warn)" },
            { key: "rule_6_1_a_b",       label: "Rule 6(1)(a)-(b): Manufacturer Identity / Generic Name", color: "var(--info)" }
        ];

        defectBarsContainer.innerHTML = "";
        DEFECT_LABELS.forEach(def => {
            const count = defects[def.key] || 0;
            const pct = Math.round((count / Math.max(1, total)) * 100);

            const row = document.createElement("div");
            row.className = "defect-bar-row";
            row.innerHTML = `
                <div class="defect-bar-info">
                    <span class="defect-rule-name">${def.label}</span>
                    <span class="defect-rule-count">${count} products (${pct}%)</span>
                </div>
                <div class="defect-bar-track">
                    <div class="defect-bar-fill" style="width: ${pct}%; background: ${def.color};"></div>
                </div>
            `;
            defectBarsContainer.appendChild(row);
        });
    }

    function filterAndRenderLedger() {
        if (!analyticsDataCache) return;
        const allProducts = analyticsDataCache.products || [];

        const filtered = allProducts.filter(p => {
            const matchesStatus = (ledgerFilterStatus === "ALL") || (p.overall_status === ledgerFilterStatus);
            const matchesSearch = !ledgerSearchQuery ||
                p.product_name.toLowerCase().includes(ledgerSearchQuery) ||
                p.inspection_id.toLowerCase().includes(ledgerSearchQuery);
            return matchesStatus && matchesSearch;
        });

        ledgerProductCount.textContent = `${filtered.length} of ${allProducts.length} items`;
        ledgerTableBody.innerHTML = "";

        if (filtered.length === 0) {
            ledgerTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:24px;color:var(--txt-muted);">No products match the selected criteria.</td></tr>`;
            return;
        }

        filtered.forEach(p => {
            const st = p.overall_status;
            const statusClass = st === "PASS" ? "chip-s-pass" : (st === "WARNING" ? "chip-s-warn" : "chip-s-fail");

            let violationsText = "No defects detected";
            if (p.violations_summary?.length) {
                violationsText = p.violations_summary.map(v => `${v.rule}: ${v.details}`).join(" • ");
            }

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><span class="table-ref-code">${p.inspection_id}</span></td>
                <td class="table-product-cell">${p.product_name}</td>
                <td><span class="count-tag">${p.panels_count || 1} panel${p.panels_count > 1 ? 's' : ''}</span></td>
                <td><span class="table-status-pill ${statusClass}">${st}</span></td>
                <td><b>${p.compliance_score}%</b></td>
                <td style="max-width:320px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${violationsText}">
                    <span style="color:${st === 'PASS' ? 'var(--pass)' : (st === 'WARNING' ? 'var(--warn)' : 'var(--fail)')};">
                        ${violationsText}
                    </span>
                </td>
                <td style="color:var(--txt-dim);font-size:11px;">${p.timestamp ? new Date(p.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '—'}</td>
                <td style="text-align:right;">
                    <button class="table-btn-inspect" data-id="${p.inspection_id}">
                        Inspect
                    </button>
                </td>
            `;

            tr.querySelector(".table-btn-inspect").addEventListener("click", () => {
                inspectProductById(p.inspection_id);
            });

            ledgerTableBody.appendChild(tr);
        });
    }

    // ══════════════════════════════════════════
    // CANVAS ENGINE & BOUNDING BOX OVERLAYS
    // ══════════════════════════════════════════

    function fitToView() {
        if (!currentImage) return;
        const cW = canvasContainer.clientWidth - 32;
        const cH = canvasContainer.clientHeight - 32;
        zoomLevel = Math.min(cW / currentImage.width, cH / currentImage.height, 1.5);
        redraw();
    }

    function setZoom(z) {
        zoomLevel = Math.max(0.15, Math.min(z, 5));
        redraw();
    }

    function zoomToBBox(bbox) {
        if (!currentImage || !bbox) return;
        const [bx, by, bw, bh] = bbox;
        const cx = bx + bw / 2;
        const cy = by + bh / 2;
        zoomLevel = Math.min(canvasContainer.clientWidth / bw * 0.6, 4.0);

        redraw();

        const scrollX = cx * zoomLevel - canvasContainer.clientWidth / 2;
        const scrollY = cy * zoomLevel - canvasContainer.clientHeight / 2;
        canvasContainer.scrollTo({ left: scrollX, top: scrollY, behavior: "smooth" });
    }

    function highlightRule(key) {
        highlightedRuleKey = key;
        document.querySelectorAll(".rule-card").forEach(c =>
            c.classList.toggle("highlighted", c.dataset.rule === key)
        );
        redraw();
    }

    function redraw() {
        if (!currentImage) return;

        canvas.width  = currentImage.width * zoomLevel;
        canvas.height = currentImage.height * zoomLevel;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(currentImage, 0, 0, canvas.width, canvas.height);

        if (!showOverlays || !currentAuditData) return;

        const panel = (currentAuditData.panels || [])[activePanelIndex];
        if (!panel) return;

        const rep = currentAuditData.audit_report || {};
        const tokens = panel.raw_tokens || [];

        tokens.forEach(t => {
            if (!t.bbox) return;
            const [x, y, w, h] = t.bbox;
            const rx = x * zoomLevel, ry = y * zoomLevel;
            const rw = w * zoomLevel, rh = h * zoomLevel;

            const match = matchRuleForBBox(t.bbox, rep);

            let stroke, fill, lineW;
            if (match) {
                const isHL = highlightedRuleKey && match.ruleKey === highlightedRuleKey;
                if (match.status === "COMPLIANT") {
                    stroke = isHL ? "#34d399" : "rgba(16,185,129,0.8)";
                    fill   = isHL ? "rgba(16,185,129,0.25)" : "rgba(16,185,129,0.1)";
                    lineW  = isHL ? 3 : 2;
                } else if (match.status === "WARNING") {
                    stroke = isHL ? "#fbbf24" : "rgba(245,158,11,0.8)";
                    fill   = isHL ? "rgba(245,158,11,0.25)" : "rgba(245,158,11,0.1)";
                    lineW  = isHL ? 3 : 2;
                } else {
                    stroke = isHL ? "#f87171" : "rgba(239,68,68,0.85)";
                    fill   = isHL ? "rgba(239,68,68,0.3)" : "rgba(239,68,68,0.12)";
                    lineW  = isHL ? 3.5 : 2;
                }
                if (isHL) stroke = "#818cf8";
            } else {
                stroke = "rgba(59,130,246,0.45)";
                fill   = "rgba(59,130,246,0.06)";
                lineW  = 1;
            }

            ctx.lineWidth   = lineW;
            ctx.strokeStyle = stroke;
            ctx.fillStyle   = fill;
            ctx.fillRect(rx, ry, rw, rh);
            ctx.strokeRect(rx, ry, rw, rh);

            if (match && rh > 12) {
                const lbl = match.rule;
                ctx.font = `bold ${Math.max(8, 9 * zoomLevel)}px Inter, sans-serif`;
                const tw = ctx.measureText(lbl).width;
                ctx.fillStyle = stroke;
                ctx.fillRect(rx, Math.max(0, ry - 14 * Math.min(zoomLevel, 1)), tw + 6, 14 * Math.min(zoomLevel, 1));
                ctx.fillStyle = "#fff";
                ctx.fillText(lbl, rx + 3, Math.max(10, ry - 3 * Math.min(zoomLevel, 1)));
            }
        });
    }

    function matchRuleForBBox(bbox, rep) {
        for (const [rKey, rVal] of Object.entries(rep)) {
            const ref = rVal.bbox_reference;
            if (Array.isArray(ref) && Math.abs(ref[0] - bbox[0]) < 14 && Math.abs(ref[1] - bbox[1]) < 14) {
                return { ruleKey: rKey, rule: rVal.rule, status: rVal.status };
            }
        }
        return null;
    }

    canvas.addEventListener("mousemove", e => {
        if (!currentAuditData) return;
        const rect   = canvas.getBoundingClientRect();
        const mx     = (e.clientX - rect.left) / zoomLevel;
        const my     = (e.clientY - rect.top) / zoomLevel;
        const panel  = (currentAuditData.panels || [])[activePanelIndex];
        if (!panel) return;

        hoveredToken = null;
        for (const t of panel.raw_tokens || []) {
            const [x, y, w, h] = t.bbox;
            if (mx >= x && mx <= x + w && my >= y && my <= y + h) {
                hoveredToken = t;
                break;
            }
        }

        if (hoveredToken) {
            const match = matchRuleForBBox(hoveredToken.bbox, currentAuditData.audit_report || {});
            let tip = `<b>"${hoveredToken.text}"</b>`;
            if (match) tip += `<br><span style="color:var(--accent)">${match.rule} · ${match.status}</span>`;
            tooltip.innerHTML = tip;
            tooltip.style.left = `${e.clientX + 14}px`;
            tooltip.style.top  = `${e.clientY + 14}px`;
            tooltip.classList.remove("hidden");
        } else {
            tooltip.classList.add("hidden");
        }
    });

    canvas.addEventListener("mouseleave", () => tooltip.classList.add("hidden"));

    canvas.addEventListener("click", () => {
        if (!hoveredToken || !currentAuditData) return;
        const match = matchRuleForBBox(hoveredToken.bbox, currentAuditData.audit_report || {});
        if (match?.ruleKey) {
            highlightRule(match.ruleKey);
            document.getElementById(`card-${match.ruleKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    });

    canvasContainer.addEventListener("wheel", e => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            setZoom(e.deltaY < 0 ? zoomLevel * 1.1 : zoomLevel / 1.1);
        }
    }, { passive: false });

    function showLoader(visible, text) {
        loader.classList.toggle("hidden", !visible);
        clearInterval(loaderStageTimer);
        if (text && loaderStatusText) loaderStatusText.textContent = text;
        if (visible) {
            dropZone.classList.add("hidden");
            canvasWrapper.classList.add("hidden");
            const stages = [text || "Preparing audit…", "Enhancing packaging image…", "Reading declarations…", "Checking statutory rules…"];
            let stage = 0;
            loaderStageTimer = setInterval(() => {
                stage = Math.min(stage + 1, stages.length - 1);
                loaderStatusText.textContent = stages[stage];
            }, 950);
        }
    }

    // Initialize badge on startup
    refreshAnalyticsBadge();
});
