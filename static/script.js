/**
 * LM Audit · SIH26034
 * Frontend Controller — Clean UI Edition
 */

document.addEventListener("DOMContentLoaded", () => {
    // ── State ──────────────────────────────────
    let currentAuditData    = null;
    let activePanelIndex    = 0;
    let currentImage        = null;
    let zoomLevel           = 1.0;
    let showOverlays        = true;
    let hoveredToken        = null;
    let highlightedRuleKey  = null;

    // ── DOM ────────────────────────────────────
    const canvas         = document.getElementById("inspection-canvas");
    const ctx            = canvas.getContext("2d");
    const canvasContainer= document.getElementById("canvas-container");
    const canvasWrapper  = document.getElementById("canvas-wrapper");
    const dropZone       = document.getElementById("drop-placeholder");
    const loader         = document.getElementById("processing-loader");
    const tooltip        = document.getElementById("canvas-tooltip");
    const imageUpload    = document.getElementById("image-upload");
    const panelTabsBar   = document.getElementById("panel-tabs-bar");
    const auditContent   = document.getElementById("audit-content");
    const panelCounter   = document.getElementById("panel-counter");
    const metaTag        = document.getElementById("inspection-meta-tag");
    const toggleOverlay  = document.getElementById("toggle-overlay");
    const btnZoomIn      = document.getElementById("btn-zoom-in");
    const btnZoomOut     = document.getElementById("btn-zoom-out");
    const btnZoomReset   = document.getElementById("btn-zoom-reset");
    const btnExportPdf   = document.getElementById("btn-export-pdf");
    const btnRawJson     = document.getElementById("btn-raw-json");
    const jsonModal      = document.getElementById("json-modal");
    const btnCloseModal  = document.getElementById("btn-close-modal");
    const btnCopyJson    = document.getElementById("btn-copy-json");
    const jsonDisplay    = document.querySelector("#json-display code");

    // ── Sample chips ───────────────────────────
    document.querySelectorAll(".chip[data-sample]").forEach(btn => {
        btn.addEventListener("click", () => loadSample(btn.dataset.sample));
    });

    // ── File upload ────────────────────────────
    imageUpload.addEventListener("change", e => {
        if (e.target.files?.length) uploadFiles(e.target.files);
    });

    // ── Drag & drop ────────────────────────────
    canvasContainer.addEventListener("dragover", e => {
        e.preventDefault();
        canvasContainer.classList.add("drag-hover");
    });
    canvasContainer.addEventListener("dragleave", () => canvasContainer.classList.remove("drag-hover"));
    canvasContainer.addEventListener("drop", e => {
        e.preventDefault();
        canvasContainer.classList.remove("drag-hover");
        if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
    });

    // ── Zoom ───────────────────────────────────
    btnZoomIn.addEventListener("click",    () => setZoom(zoomLevel * 1.3));
    btnZoomOut.addEventListener("click",   () => setZoom(zoomLevel / 1.3));
    btnZoomReset.addEventListener("click", () => fitToView());
    toggleOverlay.addEventListener("change", e => { showOverlays = e.target.checked; redraw(); });

    // ── Modal ──────────────────────────────────
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
        setTimeout(() => btnCopyJson.textContent = "Copy", 2000);
    });

    // ── PDF Export ─────────────────────────────
    btnExportPdf.addEventListener("click", exportPdf);

    // ══════════════════════════════════════════
    // API
    // ══════════════════════════════════════════

    async function loadSample(name) {
        showLoader(true);
        try {
            const res = await fetch(`/api/sample/${name}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            renderResult(await res.json());
        } catch (err) {
            alert("Failed to load sample: " + err.message);
        } finally {
            showLoader(false);
        }
    }

    async function uploadFiles(fileList) {
        showLoader(true);
        const fd = new FormData();
        for (const f of fileList) fd.append("files", f);
        try {
            const res = await fetch("/api/audit", { method: "POST", body: fd });
            if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Upload error"); }
            renderResult(await res.json());
        } catch (err) {
            alert("Audit failed: " + err.message);
        } finally {
            showLoader(false);
        }
    }

    async function exportPdf() {
        if (!currentAuditData) return;
        btnExportPdf.disabled = true;
        btnExportPdf.innerHTML = "Generating…";
        try {
            const payload = {
                inspection_id:    currentAuditData.inspection_id,
                commodity_name:   currentAuditData.audit_report?.rule_6_1_b_commodity_name?.detected_value || "Packaged Commodity",
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
                download: `LM_Audit_${currentAuditData.inspection_id}.pdf`
            });
            document.body.appendChild(a); a.click(); a.remove();
        } catch (err) {
            alert("PDF export failed: " + err.message);
        } finally {
            btnExportPdf.disabled = false;
            btnExportPdf.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> Export PDF`;
        }
    }

    // ══════════════════════════════════════════
    // RENDER
    // ══════════════════════════════════════════

    function renderResult(data) {
        currentAuditData   = data;
        activePanelIndex   = 0;
        highlightedRuleKey = null;

        btnExportPdf.disabled = false;
        btnRawJson.disabled   = false;
        metaTag.textContent   = `Ref: ${data.inspection_id}`;

        const panels = data.panels || [];

        // Multi-panel tabs
        if (panels.length > 1) {
            panelTabsBar.classList.remove("hidden");
            panelTabsBar.innerHTML = "";
            panels.forEach((p, i) => {
                const btn = Object.assign(document.createElement("button"), {
                    className: `panel-tab${i === 0 ? " active" : ""}`,
                    textContent: `Panel ${i + 1}`
                });
                btn.addEventListener("click", () => switchPanel(i));
                panelTabsBar.appendChild(btn);
            });
        } else {
            panelTabsBar.classList.add("hidden");
        }

        renderAuditCards(data);
        loadPanel(0);
    }

    function switchPanel(idx) {
        activePanelIndex = idx;
        document.querySelectorAll(".panel-tab").forEach((t, i) => t.classList.toggle("active", i === idx));
        loadPanel(idx);
    }

    function loadPanel(idx) {
        const p = (currentAuditData.panels || [])[idx];
        if (!p) return;
        panelCounter.textContent = (currentAuditData.panels || []).length > 1
            ? `Panel ${idx + 1} / ${currentAuditData.panels.length}` : "Label Preview";

        const img = new Image();
        img.onload = () => {
            currentImage = img;
            dropZone.classList.add("hidden");
            canvasWrapper.classList.remove("hidden");
            fitToView();
        };
        img.src = p.image_b64;
    }

    function renderAuditCards(data) {
        const st    = data.overall_status;
        const score = data.compliance_score;
        const rep   = data.audit_report || {};

        const pillClass = st === "PASS" ? "pill-pass" : st === "WARNING" ? "pill-warn" : "pill-fail";
        const barColor  = st === "PASS" ? "var(--pass)" : st === "WARNING" ? "var(--warn)" : "var(--fail)";

        let html = `
        <div class="summary-card">
            <div class="summary-top">
                <div class="verdict-pill ${pillClass}">
                    <div class="verdict-dot"></div>
                    ${st}
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
                    <div class="stat-lbl">Passed</div>
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

        // Violations box
        if (data.violations_summary?.length) {
            html += `<div class="violations-box">
                <div class="violations-box-title">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    ${data.violations_summary.length} Statutory Issue${data.violations_summary.length !== 1 ? "s" : ""}
                </div>
                <ul class="violations-list">
                    ${data.violations_summary.map(v => `<li><b>${v.rule}:</b> ${v.details}</li>`).join("")}
                </ul>
            </div>`;
        }

        // Rule cards
        const RULES = [
            { key: "rule_6_1_e_mrp",              label: "MRP & Tax Declaration" },
            { key: "rule_6_1_c_net_quantity",      label: "Net Quantity & SI Unit" },
            { key: "rule_6_1_11_unit_sale_price",  label: "Unit Sale Price (Math)" },
            { key: "rule_6_1_d_mfg_date",          label: "Mfg / Packing Date" },
            { key: "rule_6_1_da_consumer_grievance",label: "Consumer Grievance" },
            { key: "rule_6_1_a_manufacturer",      label: "Manufacturer Identity" },
            { key: "rule_6_1_b_commodity_name",    label: "Commodity Name" },
        ];

        html += `<div style="display:flex;flex-direction:column;gap:8px;">`;
        for (const r of RULES) {
            const rd = rep[r.key];
            if (!rd) continue;
            const s  = rd.status || "FAIL";
            const isOk = s === "COMPLIANT";
            const isWarn = s === "WARNING";
            const chipC   = isOk ? "chip-s-pass" : isWarn ? "chip-s-warn" : "chip-s-fail";
            const detailC = isOk ? "detail-pass" : isWarn ? "detail-warn" : "detail-fail";
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
                        <span class="det-label">Detected</span>
                        <span class="det-value">${rd.detected_value || "—"}</span>
                    </div>
                    <div class="clause-quote">${rd.legal_clause || ""}</div>
                    <div class="detail-box ${detailC}">${rd.details || ""}</div>
                    ${bbox ? `<button class="focus-btn" data-bbox="${rd.bbox_reference.join(",")}">
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                        Focus
                    </button>` : ""}
                </div>
            </div>`;
        }
        html += `</div>`;

        auditContent.innerHTML = html;

        // Listeners
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

    function highlightRule(key) {
        highlightedRuleKey = key;
        document.querySelectorAll(".rule-card").forEach(c =>
            c.classList.toggle("highlighted", c.dataset.rule === key)
        );
        redraw();
    }

    // ══════════════════════════════════════════
    // CANVAS
    // ══════════════════════════════════════════

    function fitToView() {
        if (!currentImage) return;
        const cW = canvasContainer.clientWidth  - 32;
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

        // Scroll the canvas viewport to center the bbox
        const scrollX = cx * zoomLevel - canvasContainer.clientWidth  / 2;
        const scrollY = cy * zoomLevel - canvasContainer.clientHeight / 2;
        canvasContainer.scrollTo({ left: scrollX, top: scrollY, behavior: "smooth" });
    }

    function redraw() {
        if (!currentImage) return;

        canvas.width  = currentImage.width  * zoomLevel;
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
                if (isHL) stroke = "#818cf8"; // always indigo when highlighted by rule card
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

            // Tiny label tag
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
            if (Array.isArray(ref) && Math.abs(ref[0] - bbox[0]) < 12 && Math.abs(ref[1] - bbox[1]) < 12) {
                return { ruleKey: rKey, rule: rVal.rule, status: rVal.status };
            }
        }
        return null;
    }

    // ── Mouse events ───────────────────────────
    canvas.addEventListener("mousemove", e => {
        if (!currentAuditData) return;
        const rect   = canvas.getBoundingClientRect();
        const mx     = (e.clientX - rect.left)  / zoomLevel;
        const my     = (e.clientY - rect.top)   / zoomLevel;
        const panel  = (currentAuditData.panels || [])[activePanelIndex];
        if (!panel) return;

        hoveredToken = null;
        for (const t of panel.raw_tokens || []) {
            const [x, y, w, h] = t.bbox;
            if (mx >= x && mx <= x + w && my >= y && my <= y + h) { hoveredToken = t; break; }
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

    // Wheel zoom on canvas
    canvasContainer.addEventListener("wheel", e => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            setZoom(e.deltaY < 0 ? zoomLevel * 1.1 : zoomLevel / 1.1);
        }
    }, { passive: false });

    // ── Helpers ────────────────────────────────
    function showLoader(v) {
        loader.classList.toggle("hidden", !v);
        if (v) {
            dropZone.classList.add("hidden");
            canvasWrapper.classList.add("hidden");
        }
    }
});
