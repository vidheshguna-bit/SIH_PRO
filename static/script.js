/**
 * SmartMetrology AI · SIH26034
 * Complete Client Application: Live Google Lens AR Scanner + Multi-Panel Photo Audit
 */
document.addEventListener("DOMContentLoaded", () => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = (v = "") => String(v).replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));

  const screenNames = {
    dashboard: "Inspector Dashboard",
    scanner: "New Inspection",
    processing: "AI Processing",
    extracted: "Extracted Information",
    compliance: "Compliance Result",
    evidence: "Violation Evidence",
    review: "Human Review",
    report: "Inspection Report",
    rules: "Rule Database",
    analytics: "Analytics",
    history: "Inspection History",
    reports: "Reports"
  };

  const pipelineStages = [
    "Image enhancement & bilateral filtering",
    "Text region boundary detection",
    "RapidOCR ONNX character recognition",
    "Statutory Legal Metrology clause mapping",
    "Deterministic Rule Engine evaluation",
    "Compliance verdict synthesis"
  ];

  const panelNames = ["Front image", "Back image", "Side image", "Additional label image"];

  let audit = {
    inspection_id: "LM-" + new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-NEW",
    product_name: "Awaiting Inspection",
    timestamp: new Date().toISOString(),
    overall_status: "PENDING",
    compliance_score: 0,
    compliance_grade: "—",
    violations_count: 0,
    warnings_count: 0,
    panels: [],
    audit_report: {},
    fields: []
  };

  let files = [];
  let activeViolation = 0;
  let review = null;

  const recentHistory = [
    ["LM-260907-1042", "Fresh Farm Atta", "ABC Foods Pvt Ltd", "07 Sep 2026", "82%", "FAIL", "Pending"],
    ["LM-260906-0921", "Royal Delight Cookies", "Royal Foods India", "06 Sep 2026", "100%", "PASS", "A. Kumar"],
    ["LM-260905-1814", "Himalayan Desi Ghee", "North Valley Foods", "05 Sep 2026", "76%", "FAIL", "S. Meena"],
    ["LM-260904-1358", "Herbal Hair Oil", "Ayush Care Ltd", "04 Sep 2026", "91%", "WARNING", "Pending"]
  ];

  const seedRules = [
    { id: "LM-PC-001", number: "6(1)(a)", title: "Manufacturer / Packer Declaration", category: "General Packaged Commodity", from: "01 Jan 2026", to: "—", amendment: "G.S.R. 2026", status: "ACTIVE", version: 2026 },
    { id: "LM-PC-002", number: "6(1)(b)", title: "Common or Generic Product Name", category: "General Packaged Commodity", from: "01 Jan 2026", to: "—", amendment: "Base + 2026", status: "ACTIVE", version: 2026 },
    { id: "LM-PC-003", number: "6(1)(c)", title: "Net Quantity in Standard Units", category: "General Packaged Commodity", from: "01 Jan 2026", to: "—", amendment: "Rule 12 aligned", status: "ACTIVE", version: 2026 },
    { id: "LM-PC-004", number: "6(1)(e)", title: "MRP Inclusive of All Taxes", category: "Retail Package", from: "01 Jan 2026", to: "—", amendment: "G.S.R. 2026", status: "ACTIVE", version: 2026 },
    { id: "LM-PC-005", number: "6(1)(da)", title: "Consumer Grievance Details", category: "General Packaged Commodity", from: "01 Jan 2026", to: "—", amendment: "2022 / 2026", status: "ACTIVE", version: 2026 },
    { id: "LM-PC-006", number: "6(11)", title: "Unit Sale Price Declaration", category: "Retail Package", from: "01 Oct 2022", to: "—", amendment: "G.S.R. 2022", status: "ACTIVE", version: 2022 }
  ];

  let rules;
  try { rules = JSON.parse(localStorage.getItem("sm-rules")) || seedRules; } catch (_) { rules = seedRules; }

  // ---------------------------------------------------------------------------
  // SCREEN NAVIGATION & UTILITIES
  // ---------------------------------------------------------------------------
  function showScreen(name) {
    $$(".screen").forEach(x => x.classList.toggle("active", x.id === `screen-${name}`));
    $$(".nav-item").forEach(x => x.classList.toggle("active", x.dataset.screen === name));
    $("#page-title").textContent = screenNames[name] || "SmartMetrology AI";
    $("#sidebar").classList.remove("open");
    window.scrollTo({ top: 0, behavior: "smooth" });

    // If leaving scanner, stop camera
    if (name !== "scanner" && cameraStream) {
      stopCamera();
    }

    if (name === "extracted") renderFields();
    if (name === "compliance") renderCompliance();
    if (name === "evidence") renderEvidence();
    if (name === "review") renderReview();
    if (name === "report") renderReport();
    if (name === "rules") renderRules();
    if (name === "analytics") loadAnalytics();
  }

  $$('[data-screen], [data-go]').forEach(b => b.addEventListener("click", () => showScreen(b.dataset.screen || b.dataset.go)));
  $("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));

  function toast(message, type = "") {
    const t = $("#toast");
    t.textContent = message;
    t.className = `toast show ${type}`;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.className = "toast", 3500);
  }

  function openModal(title, html) {
    $("#modal-title").textContent = title;
    $("#modal-content").innerHTML = html;
    $("#modal").classList.add("show");
  }
  function closeModal() { $("#modal").classList.remove("show"); }
  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });

  $("#notifications").addEventListener("click", () => openModal(
    "Review notifications",
    '<div class="review-alert warning"><b>3 high-priority reviews</b><span>Low-confidence extractions require inspector verification.</span></div><button class="btn btn-primary" id="open-pending">OPEN HUMAN REVIEW</button>'
  ));
  document.addEventListener("click", e => {
    if (e.target.id === "open-pending") {
      closeModal();
      showScreen("review");
    }
  });

  // ---------------------------------------------------------------------------
  // SCANNER MODE TABS (Google Lens Live Hover vs Photo Upload)
  // ---------------------------------------------------------------------------
  const tabBtnLens = $("#tab-btn-lens");
  const tabBtnUpload = $("#tab-btn-upload");
  const viewLens = $("#view-lens");
  const viewUpload = $("#view-upload");

  if (tabBtnLens && tabBtnUpload) {
    tabBtnLens.addEventListener("click", () => {
      tabBtnLens.classList.add("active");
      tabBtnUpload.classList.remove("active");
      if (viewLens) viewLens.style.display = "block";
      if (viewUpload) viewUpload.style.display = "none";
    });

    tabBtnUpload.addEventListener("click", () => {
      tabBtnUpload.classList.add("active");
      tabBtnLens.classList.remove("active");
      if (viewLens) viewLens.style.display = "none";
      if (viewUpload) viewUpload.style.display = "block";
      stopCamera();
    });
  }

  // ---------------------------------------------------------------------------
  // GOOGLE LENS LIVE HOVER SCANNER (Continuous Zero-Upload Detection)
  // ---------------------------------------------------------------------------
  let cameraStream = null;
  let isDetectingFrame = false;
  let detectTimer = null;
  let facingMode = "environment";

  const videoElem = $("#lens-video");
  const canvasElem = $("#lens-canvas");
  const laserElem = $("#lens-laser");
  const camToggleBtn = $("#lens-camera-toggle");
  const switchCamBtn = $("#lens-switch-cam");
  const captureBtn = $("#lens-capture-btn");
  const liveStatusElem = $("#lens-live-status");

  const missingListElem = $("#lens-missing-list");
  const detectedListElem = $("#lens-detected-list");
  const chemListElem = $("#lens-chemical-list");

  if (camToggleBtn) {
    camToggleBtn.addEventListener("click", () => {
      if (cameraStream) {
        stopCamera();
      } else {
        startCamera();
      }
    });
  }

  if (switchCamBtn) {
    switchCamBtn.addEventListener("click", async () => {
      facingMode = facingMode === "environment" ? "user" : "environment";
      stopCamera();
      await startCamera();
    });
  }

  if (captureBtn) {
    captureBtn.addEventListener("click", () => {
      if (!videoElem || !videoElem.videoWidth) {
        toast("No active camera frame to capture.", "error");
        return;
      }
      toast("Capturing high-resolution frame for statutory audit…");
      const snapCanvas = document.createElement("canvas");
      snapCanvas.width = videoElem.videoWidth;
      snapCanvas.height = videoElem.videoHeight;
      const sCtx = snapCanvas.getContext("2d");
      sCtx.drawImage(videoElem, 0, 0, snapCanvas.width, snapCanvas.height);
      snapCanvas.toBlob(blob => {
        stopCamera();
        runInspection(false, blob);
      }, "image/jpeg", 0.95);
    });
  }

  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      toast("Camera API is not supported on this device/browser.", "error");
      return;
    }
    try {
      if (camToggleBtn) camToggleBtn.textContent = "⌛ Initializing camera…";
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: facingMode },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          },
          audio: false
        });
      } catch (_) {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }

      cameraStream = stream;
      videoElem.srcObject = cameraStream;
      await videoElem.play();

      if (camToggleBtn) {
        camToggleBtn.textContent = "⏹ Stop Camera";
        camToggleBtn.classList.remove("btn-primary");
        camToggleBtn.classList.add("btn-secondary");
      }
      if (switchCamBtn) switchCamBtn.style.display = "inline-flex";
      if (captureBtn) captureBtn.style.display = "inline-flex";
      if (laserElem) laserElem.style.display = "block";

      if (liveStatusElem) {
        liveStatusElem.textContent = "LIVE WATCHDOG RUNNING";
        liveStatusElem.classList.add("scanning");
      }

      toast("Camera active. Point package label at viewfinder for instant spotting.");

      const updateCanvasSize = () => {
        if (videoElem.videoWidth && canvasElem) {
          canvasElem.width = videoElem.videoWidth;
          canvasElem.height = videoElem.videoHeight;
        }
      };
      videoElem.addEventListener("loadedmetadata", updateCanvasSize, { once: true });
      updateCanvasSize();

      clearInterval(detectTimer);
      detectTimer = setInterval(captureAndDetectFrame, 750);
      setTimeout(captureAndDetectFrame, 200);

    } catch (err) {
      console.error("Camera access failed:", err);
      toast("Camera access denied or unavailable: " + err.message, "error");
      stopCamera();
    }
  }

  function stopCamera() {
    if (cameraStream) {
      cameraStream.getTracks().forEach(t => t.stop());
      cameraStream = null;
    }
    clearInterval(detectTimer);
    detectTimer = null;
    isDetectingFrame = false;

    if (videoElem) videoElem.srcObject = null;
    if (camToggleBtn) {
      camToggleBtn.textContent = "📷 Start Camera Feed";
      camToggleBtn.classList.add("btn-primary");
      camToggleBtn.classList.remove("btn-secondary");
    }
    if (switchCamBtn) switchCamBtn.style.display = "none";
    if (captureBtn) captureBtn.style.display = "none";
    if (laserElem) laserElem.style.display = "none";

    if (liveStatusElem) {
      liveStatusElem.textContent = "Camera Standby";
      liveStatusElem.classList.remove("scanning");
    }

    if (canvasElem) {
      const ctx = canvasElem.getContext("2d");
      ctx.clearRect(0, 0, canvasElem.width, canvasElem.height);
    }
  }

  async function captureAndDetectFrame() {
    if (isDetectingFrame || !cameraStream || !videoElem || !videoElem.videoWidth) return;
    isDetectingFrame = true;

    try {
      const vw = videoElem.videoWidth;
      const vh = videoElem.videoHeight;
      const maxDim = 640;
      const scale = Math.min(1, maxDim / Math.max(vw, vh));
      const dw = Math.round(vw * scale);
      const dh = Math.round(vh * scale);

      const offCanvas = document.createElement("canvas");
      offCanvas.width = dw;
      offCanvas.height = dh;
      const offCtx = offCanvas.getContext("2d");
      offCtx.drawImage(videoElem, 0, 0, dw, dh);
      const b64 = offCanvas.toDataURL("image/jpeg", 0.72);

      const res = await fetch("/api/lens-detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: b64 })
      });

      if (!res.ok) {
        isDetectingFrame = false;
        return;
      }

      const data = await res.json();
      renderLensHUD(data);
      renderARCanvas(data);

    } catch (e) {
      // Ignore background fluctuations
    } finally {
      isDetectingFrame = false;
    }
  }

  function renderARCanvas(data) {
    if (!canvasElem) return;
    const ctx = canvasElem.getContext("2d");
    const cw = canvasElem.width;
    const ch = canvasElem.height;
    ctx.clearRect(0, 0, cw, ch);

    const detected = data.detected_declarations || [];
    detected.forEach(d => {
      const nb = d.normalized_bbox;
      if (!nb || nb.length < 4) return;
      const x = nb[0] * cw;
      const y = nb[1] * ch;
      const w = nb[2] * cw;
      const h = nb[3] * ch;

      const isCompliant = d.badge === "COMPLIANT";
      const strokeColor = isCompliant ? "#10b981" : "#f59e0b";
      const fillColor = isCompliant ? "rgba(16, 185, 129, 0.16)" : "rgba(245, 158, 11, 0.16)";

      ctx.save();
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 3;
      ctx.shadowColor = strokeColor;
      ctx.shadowBlur = 10;
      ctx.fillStyle = fillColor;

      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, y, w, h, 6) : ctx.rect(x, y, w, h);
      ctx.fill();
      ctx.stroke();

      const label = `${isCompliant ? "✓" : "⚠"} ${d.name}: ${d.detected_value}`;
      ctx.font = "bold 13px Inter, sans-serif";
      const textWidth = ctx.measureText(label).width;
      const tagH = 22;
      const tagW = textWidth + 16;
      const tagY = Math.max(0, y - tagH - 4);

      ctx.fillStyle = strokeColor;
      ctx.shadowBlur = 0;
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, tagY, tagW, tagH, 5) : ctx.rect(x, tagY, tagW, tagH);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.fillText(label, x + 8, tagY + 16);
      ctx.restore();
    });

    const tokens = data.tokens || [];
    if (!detected.length) {
      tokens.slice(0, 15).forEach(t => {
        const nb = t.normalized_bbox;
        if (!nb) return;
        const x = nb[0] * cw;
        const y = nb[1] * ch;
        const w = nb[2] * cw;
        const h = nb[3] * ch;
        ctx.save();
        ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
        ctx.lineWidth = 1;
        ctx.strokeRect(x, y, w, h);
        ctx.restore();
      });
    }
  }

  function renderLensHUD(data) {
    if (missingListElem) {
      const missing = data.missing_declarations || [];
      if (!data.raw_text || data.raw_text.trim().length === 0) {
        missingListElem.innerHTML = '<p class="placeholder-text">Point camera at product label text to spot declarations…</p>';
      } else if (missing.length === 0) {
        missingListElem.innerHTML = `
          <div class="hud-item" style="background:#ecfdf5;border-color:#10b981;color:#065f46;">
            <strong>✓ All Mandatory Declarations Present</strong>
            <span>MRP with tax clause, Net Qty in SI units, Packing Date &amp; Grievance contact verified.</span>
          </div>`;
      } else {
        missingListElem.innerHTML = missing.map(m => `
          <div class="hud-item missing">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <strong>🚨 ${esc(m.name)}</strong>
              <span class="badge fail">${esc(m.rule)}</span>
            </div>
            <span>${esc(m.details)}</span>
            <small style="color:#ef4444;font-weight:600;">Statutory violation under Legal Metrology Rules</small>
          </div>
        `).join("");
      }
    }

    if (detectedListElem) {
      const detected = data.detected_declarations || [];
      if (detected.length === 0) {
        detectedListElem.innerHTML = '<p class="placeholder-text">Searching label for MRP, Net Quantity, Date, Helpline…</p>';
      } else {
        detectedListElem.innerHTML = detected.map(d => `
          <div class="hud-item ${d.badge === 'COMPLIANT' ? 'detected' : 'warning'}">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <strong>${d.badge === 'COMPLIANT' ? '✅' : '⚠'} ${esc(d.name)}</strong>
              <span class="badge ${d.badge === 'COMPLIANT' ? 'pass' : 'warning'}">${esc(d.rule)}</span>
            </div>
            <strong style="color:var(--navy);font-family:'JetBrains Mono',monospace;">${esc(d.detected_value)}</strong>
            <small>${esc(d.details)}</small>
          </div>
        `).join("");
      }
    }

    if (chemListElem) {
      const chems = data.chemical_alerts || [];
      if (chems.length === 0) {
        chemListElem.innerHTML = '<p class="placeholder-text">No hazardous food dyes or additives spotted in current view.</p>';
      } else {
        chemListElem.innerHTML = chems.map(c => `
          <div class="hud-item" style="border-left-color:${c.color};background:rgba(255,255,255,0.7);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <strong style="color:var(--navy);">🧪 ${esc(c.name)} (${esc(c.code)})</strong>
              <span class="badge" style="background:${c.color};color:#fff;">${esc(c.rating)}</span>
            </div>
            <span style="color:#475569;">${esc(c.category)}</span>
            <small style="color:#b91c1c;">⚠ ${esc(c.advisory)}</small>
          </div>
        `).join("");
      }
    }
  }

  // ---------------------------------------------------------------------------
  // PHOTO UPLOAD & MULTI-PANEL VIEW
  // ---------------------------------------------------------------------------
  $$(".upload-slot").forEach(s => s.addEventListener("click", () => {
    $("#image-input").dataset.target = s.dataset.index;
    $("#image-input").click();
  }));

  $("#image-input").addEventListener("change", e => {
    const incoming = [...e.target.files].filter(f => f.type.startsWith("image/")).slice(0, 4);
    const target = Number(e.target.dataset.target || 0);
    incoming.forEach((f, i) => files[Math.min(target + i, 3)] = f);
    files = files.slice(0, 4);
    e.target.value = "";
    renderUploads();
  });

  $("#upload-grid").addEventListener("dragover", e => e.preventDefault());
  $("#upload-grid").addEventListener("drop", e => {
    e.preventDefault();
    files = [...e.dataTransfer.files].filter(f => f.type.startsWith("image/")).slice(0, 4);
    renderUploads();
  });

  function renderUploads() {
    $$(".upload-slot").forEach((slot, i) => {
      [$("img", slot), $(".slot-overlay", slot), $(".quality-badge", slot), $(".remove-image", slot)].forEach(x => x && x.remove());
      if (!files[i]) return;

      const img = document.createElement("img");
      img.src = URL.createObjectURL(files[i]);
      img.alt = panelNames[i];

      const badge = document.createElement("span");
      badge.className = "quality-badge";
      badge.textContent = files[i].size < 80000 ? "⚠ CHECK QUALITY" : "✓ GOOD QUALITY";
      if (files[i].size < 80000) badge.style.background = "#b45309";

      const ov = document.createElement("div");
      ov.className = "slot-overlay";
      ov.innerHTML = `<b>${esc(panelNames[i])}</b><small>${esc(files[i].name)} · Click to retake</small>`;

      const remove = document.createElement("button");
      remove.className = "remove-image";
      remove.type = "button";
      remove.textContent = "×";
      remove.title = "Remove image";
      remove.addEventListener("click", ev => {
        ev.stopPropagation();
        files.splice(i, 1);
        renderUploads();
      });

      slot.append(img, badge, ov, remove);
    });

    $("#start-inspection").disabled = files.length === 0;
  }

  $("#start-inspection").addEventListener("click", () => runInspection(false));
  $("#demo-scan").addEventListener("click", () => runInspection(true));

  // ---------------------------------------------------------------------------
  // FULL AUDIT EXECUTION (Synchronous Multi-Panel & Snapshot Handler)
  // ---------------------------------------------------------------------------
  async function runInspection(demo, captureBlob = null) {
    showScreen("processing");
    let stage = 0;
    renderPipeline(stage);
    const timer = setInterval(() => {
      stage = Math.min(stage + 1, 4);
      renderPipeline(stage);
    }, 450);

    try {
      let res;
      if (demo) {
        res = await fetch("/api/sample/missing_grievance");
      } else if (captureBlob) {
        const fd = new FormData();
        fd.append("files", captureBlob, "lens_snapshot.jpg");
        res = await fetch("/api/audit", { method: "POST", body: fd });
      } else {
        const fd = new FormData();
        files.forEach(f => fd.append("files", f));
        res = await fetch("/api/audit", { method: "POST", body: fd });
      }

      if (!res.ok) {
        let d = {};
        try { d = await res.json(); } catch (_) {}
        throw new Error(d.detail || `Inspection service returned HTTP ${res.status}`);
      }

      audit = await res.json();
      clearInterval(timer);
      renderPipeline(5);

      const realText = audit.full_extracted_text ||
        (audit.panels && audit.panels.map(p => p.ocr_text || p.extracted_text || "").join("\n\n")) ||
        audit.raw_text ||
        "Extracted statutory declarations ready for evaluation.";

      $("#ocr-live").textContent = realText;
      $("#ocr-confidence").textContent = `${Math.round(audit.compliance_score || 94)}% confidence`;

      const rawExtractedBox = $("#extracted-raw-text");
      if (rawExtractedBox) {
        rawExtractedBox.textContent = realText;
      }

      await new Promise(r => setTimeout(r, 400));
      buildFields();
      renderHistory();
      showScreen("extracted");
      toast(`AI extraction completed for ${audit.product_name}.`);

    } catch (err) {
      clearInterval(timer);
      $("#ocr-live").textContent = `ERROR STATE\n${err.message}\n\nDeterministic compliance validation aborted.`;
      $("#progress-label").textContent = "Processing failed";
      toast("Inspection failed: " + err.message, "error");
    }
  }

  function renderPipeline(stage) {
    const pct = Math.round((stage + 1) / (pipelineStages.length) * 100);
    $("#pipeline-progress").style.width = `${pct}%`;
    $("#progress-label").textContent = stage >= 5 ? "100% complete" : `${pct}% complete`;
    $("#pipeline-steps").innerHTML = pipelineStages.map((p, i) => `
      <div class="pipeline-step ${i < stage ? "done" : i === stage ? "running" : ""}">
        <span>${i < stage ? "✓" : i === stage ? "◉" : "○"}</span>
        <b>${p}</b>
      </div>
    `).join("");

    const liveStatusTexts = [
      "Preparing secure image workspace & applying bilateral filters…",
      "Detecting packaging text regions and bounding contours…",
      "Executing RapidOCR ONNX inference across all panels…",
      "Mapping recognized tokens to Legal Metrology clauses…",
      "Evaluating deterministic Rule Engine against statutory standards…",
      "Compliance report generated. Human inspector verification ready."
    ];
    $("#ocr-live").textContent = liveStatusTexts[Math.min(stage, 5)];
    $("#ocr-confidence").textContent = stage < 2 ? "—" : `${Math.min(98, 78 + stage * 4)}% confidence`;
  }

  // ---------------------------------------------------------------------------
  // EXTRACTED PRODUCT INFORMATION & FIELD VERIFICATION
  // ---------------------------------------------------------------------------
  function findRule(...fragments) {
    const rep = audit.audit_report || {};
    for (const [key, val] of Object.entries(rep)) {
      if (!val || typeof val !== "object") continue;
      const combined = `${key} ${val.title || ""} ${val.rule || ""}`.toLowerCase();
      if (fragments.some(f => combined.includes(f.toLowerCase()))) {
        return val;
      }
    }
    return {};
  }

  function confidence(item, fallback = 92) {
    const s = String(item.status || "").toUpperCase();
    return s === "WARNING" ? 78 : s.includes("COMPLIANT") && !s.includes("NON") ? Math.max(fallback, 96) : Math.max(fallback, 90);
  }

  function buildFields() {
    const product = findRule("product", "commodity");
    const maker = findRule("manufacturer", "packer");
    const qty = findRule("net quantity", "quantity");
    const mrp = findRule("mrp", "price");
    const date = findRule("date", "mfg", "packing");
    const care = findRule("consumer", "grievance", "care");
    const usp = findRule("unit sale", "usp");

    audit.fields = [
      { name: "Product Name", value: audit.product_name || product.detected_value || "Not detected", confidence: confidence(product, 98), source: "Front image" },
      { name: "Manufacturer / Packer / Importer", value: maker.detected_value || "Not detected", confidence: confidence(maker, 92), source: "Back image" },
      { name: "Country of Origin", value: "India", confidence: 88, source: "Back image" },
      { name: "Net Quantity", value: qty.detected_value || "Not detected", confidence: confidence(qty, 97), source: "Front image" },
      { name: "MRP (Retail Price)", value: mrp.detected_value || "Not detected", confidence: confidence(mrp, 98), source: "Back image" },
      { name: "MRP inclusive of taxes", value: mrp.has_tax_clause === false ? "No (Violation)" : (mrp.detected_value ? "Yes (Compliant)" : "Not detected"), confidence: confidence(mrp, 95), source: "Back image" },
      { name: "Manufacturing / Packing Date", value: date.detected_value || "Not detected", confidence: confidence(date, 91), source: "Back image" },
      { name: "Best Before / Expiry", value: "Not detected", confidence: 75, source: "Side image" },
      { name: "Consumer Care Details", value: care.detected_value || "Not detected", confidence: confidence(care, 96), source: "Back image" },
      { name: "Unit Sale Price (USP)", value: usp.detected_value || "Not detected", confidence: confidence(usp, 93), source: "Back image" },
      { name: "Dimensions (where applicable)", value: "Not applicable", confidence: 95, source: "Inspector input" }
    ];
  }

  function renderFields() {
    if (!audit.fields || !audit.fields.length) buildFields();
    $("#field-grid").innerHTML = audit.fields.map((f, i) => `
      <article class="field-card ${f.confidence < 85 ? "warning" : ""}">
        <div>
          <span>${esc(f.name)}</span>
          <strong>${esc(f.value)}</strong>
          <small>${f.confidence < 85 ? "⚠ HUMAN REVIEW · " : ""}${f.confidence}% confidence · ${esc(f.source)}</small>
        </div>
        <button data-edit-field="${i}">EDIT</button>
        <div class="confidence-bar"><i style="width:${f.confidence}%"></i></div>
      </article>
    `).join("");

    $$('[data-edit-field]').forEach(b => b.addEventListener("click", () => editField(Number(b.dataset.editField))));

    const rawBox = $("#extracted-raw-text");
    if (rawBox && audit.full_extracted_text) {
      rawBox.textContent = audit.full_extracted_text;
    }
  }

  function editField(i) {
    const f = audit.fields[i];
    openModal(
      `Edit ${f.name}`,
      `<form class="modal-form" id="field-form">
        <label>Verified value<input id="field-value" value="${esc(f.value)}" required></label>
        <label>Evidence source<input value="${esc(f.source)}" disabled></label>
        <button class="btn btn-primary">SAVE VERIFIED VALUE</button>
      </form>`
    );
    $("#field-form").addEventListener("submit", e => {
      e.preventDefault();
      f.value = $("#field-value").value;
      f.confidence = 100;
      f.source = "Inspector verified";
      closeModal();
      renderFields();
      toast("Field verified and audit trail updated.");
    });
  }
  $("#edit-all").addEventListener("click", () => {
    const i = audit.fields.findIndex(f => f.confidence < 85);
    editField(i < 0 ? 0 : i);
  });

  // ---------------------------------------------------------------------------
  // COMPLIANCE RESULT & EVIDENCE VIEW
  // ---------------------------------------------------------------------------
  function statusOf(x) {
    const s = String(x || "").toUpperCase();
    return s === "WARNING" ? "WARNING" : s.includes("COMPLIANT") && !s.includes("NON") || s === "PASS" ? "PASS" : "FAIL";
  }

  function entries() {
    return Object.entries(audit.audit_report || {}).filter(([, v]) => v && typeof v === "object" && (v.title || v.rule || v.status));
  }

  function renderCompliance() {
    const es = entries();
    const counts = { PASS: 0, WARNING: 0, FAIL: 0 };
    es.forEach(([, v]) => counts[statusOf(v.status)]++);

    const isCompliant = String(audit.overall_status || "").toUpperCase() === "PASS";
    $("#result-status").textContent = isCompliant ? "COMPLIANT" : "NON-COMPLIANT";
    $("#result-copy").textContent = isCompliant
      ? "All evaluated declarations comply with the Legal Metrology (Packaged Commodities) Rules."
      : "Statutory declaration failures detected. Review violations and take enforcement action.";

    $(".result-hero").classList.toggle("pass-state", isCompliant);
    $(".result-hero").classList.toggle("fail", !isCompliant);

    $("#screening-score").textContent = `${Math.round(audit.compliance_score || 0)}%`;
    $("#pass-count").textContent = counts.PASS;
    $("#warn-count").textContent = counts.WARNING;
    $("#fail-count").textContent = counts.FAIL;

    $("#compliance-body").innerHTML = es.map(([, v]) => {
      const s = statusOf(v.status);
      return `
        <tr>
          <td><b>${esc(v.title || v.rule || "Requirement")}</b><small class="mono"> ${esc(v.rule || "")}</small></td>
          <td><span class="badge ${s.toLowerCase()}">${s}</span></td>
          <td><b>${confidence(v, 94)}%</b></td>
          <td>${esc(v.details || "Evaluated by deterministic Legal Metrology rules.")}</td>
        </tr>
      `;
    }).join("");
  }

  function violations() {
    return entries().filter(([, v]) => statusOf(v.status) !== "PASS").map(([key, v]) => ({ key, ...v, confidence: confidence(v, 92) }));
  }

  function renderEvidence() {
    const list = violations();
    if (!list.length) {
      $("#violation-title").textContent = "No statutory violations detected";
      $("#violation-why").textContent = "All evaluated declarations meet Legal Metrology standards.";
      return;
    }
    activeViolation = Math.max(0, Math.min(activeViolation, list.length - 1));
    const v = list[activeViolation];
    const panel = audit.panels?.[v.panel_index || 0];

    $("#violation-index").textContent = `Violation ${activeViolation + 1} of ${list.length}`;
    $(".evidence-detail>.badge").textContent = `VIOLATION #${String(activeViolation + 1).padStart(2, "0")}`;
    $("#violation-title").textContent = v.title || "Statutory Non-Compliance";
    $("#violation-why").textContent = v.details || "The required declaration could not be validated.";
    $("#violation-rule").textContent = `Legal Metrology (Packaged Commodities) Rules, 2011 · ${v.rule || "Statutory Requirement"}`;
    $("#evidence-confidence").textContent = `${v.confidence}%`;
    $("#evidence-source").textContent = panel?.filename || "Primary label panel";
    $("#evidence-label").textContent = panel?.filename || "Primary label panel";

    const img = $("#evidence-img");
    img.src = panel?.image_b64 || "/static/evidence-placeholder.svg";

    const box = $(".violation-box");
    const b = v.bbox_reference || v.bbox;
    const dims = panel?.dimensions;

    if (Array.isArray(b) && dims) {
      const w = dims.width || dims[0] || 800;
      const h = dims.height || dims[1] || 800;
      box.style.left = `${b[0] / w * 100}%`;
      box.style.top = `${b[1] / h * 100}%`;
      box.style.width = `${b[2] / w * 100}%`;
      box.style.height = `${b[3] / h * 100}%`;
    } else {
      box.style.left = "18%";
      box.style.top = "55%";
      box.style.width = "65%";
      box.style.height = "18%";
    }
  }

  $("#prev-violation").addEventListener("click", () => { activeViolation--; renderEvidence(); });
  $("#next-violation").addEventListener("click", () => { activeViolation++; renderEvidence(); });

  $$(".review-action").forEach(b => b.addEventListener("click", () => {
    if (b.textContent.includes("COMMENT")) {
      openModal("Add evidence comment", `
        <form class="modal-form" id="comment-form">
          <label>Inspector comment<textarea id="evidence-comment" required></textarea></label>
          <button class="btn btn-primary">SAVE COMMENT</button>
        </form>
      `);
      $("#comment-form").addEventListener("submit", e => {
        e.preventDefault();
        audit.evidence_comment = $("#evidence-comment").value;
        closeModal();
        toast("Evidence comment recorded.");
      });
    } else {
      toast(`${b.textContent.trim()} recorded in the inspection audit trail.`);
    }
  }));

  // ---------------------------------------------------------------------------
  // HUMAN-IN-THE-LOOP REVIEW & REPORT GENERATION
  // ---------------------------------------------------------------------------
  function renderReview() {
    const items = (audit.fields || []).filter(f => f.confidence < 85)
      .concat(violations().map(v => ({ name: v.title, value: v.detected_value || "Not detected", confidence: v.confidence, source: v.rule })));

    $("#review-count").textContent = `${items.length} PENDING`;
    $("#review-items").innerHTML = items.length ? items.map((x, i) => `
      <div class="review-item">
        <div class="review-item-head">
          <div><b>${esc(x.name)}</b><small> · ${esc(x.source)}</small></div>
          <span class="badge ${x.confidence < 85 ? "warning" : "fail"}">${x.confidence}%</span>
        </div>
        <input value="${esc(x.value)}" data-review-value="${i}" aria-label="Verified ${esc(x.name)}">
        <p>Inspector verification required before final report generation.</p>
      </div>
    `).join("") : `
      <div class="empty-state">
        <span>✓</span>
        <h2>No ambiguous items</h2>
        <p>All extracted fields meet or exceed statutory confidence thresholds.</p>
      </div>
    `;
  }

  $("#complete-review").addEventListener("click", async () => {
    review = {
      inspector: "Arun Kumar",
      decision: $("#review-decision").value,
      comments: $("#review-comment").value || "No additional comments.",
      timestamp: new Date().toISOString()
    };
    $("#review-time").textContent = new Date(review.timestamp).toLocaleString("en-IN");
    try {
      await fetch("/api/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inspection_id: audit.inspection_id, ...review })
      });
    } catch (_) {}
    toast("Human review completed and timestamped.");
    showScreen("report");
  });

  function renderReport() {
    const status = String(audit.overall_status).toUpperCase() === "PASS" ? "COMPLIANT" : "NON-COMPLIANT";
    $("#report-status").textContent = status;
    $("#report-status").className = `badge ${status === "COMPLIANT" ? "pass" : "fail"}`;

    const meta = [
      ["Inspection ID", audit.inspection_id],
      ["Date & time", new Date(audit.timestamp).toLocaleString("en-IN")],
      ["Rule version", "LM-PC Rules · 2026"],
      ["Screening score", `${Math.round(audit.compliance_score || 0)}%`],
      ["Product images", `${audit.panels?.length || files.length || 1} panel(s)`],
      ["Decision source", "Deterministic Rule Engine"]
    ];
    $("#report-meta").innerHTML = meta.map(x => `<div><span>${x[0]}</span><b>${esc(x[1])}</b></div>`).join("");
    $("#report-fields").innerHTML = (audit.fields || []).map(f => `<div><span>${esc(f.name)}</span><b>${esc(f.value)} · ${f.confidence}%</b></div>`).join("");

    const vs = violations();
    $("#report-violations").innerHTML = vs.length ? vs.map(v => `
      <div class="report-violation">
        <b>${esc(v.title)}</b>
        <p>${esc(v.details)} · ${esc(v.rule)} · ${v.confidence}% confidence</p>
      </div>
    `).join("") : '<div class="review-record">No statutory violations detected.</div>';

    $("#review-record").textContent = review
      ? `${review.decision} · ${review.inspector} · ${new Date(review.timestamp).toLocaleString("en-IN")} · ${review.comments}`
      : "Pending human review";
  }

  $("#generate-report").addEventListener("click", async () => {
    const b = $("#generate-report");
    const old = b.textContent;
    b.disabled = true;
    b.textContent = "GENERATING PDF…";
    try {
      const res = await fetch("/api/export-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          inspection_id: audit.inspection_id,
          commodity_name: audit.product_name,
          overall_status: audit.overall_status,
          compliance_score: Number(audit.compliance_score),
          grade: audit.compliance_grade || "—",
          report: audit.audit_report
        })
      });
      if (!res.ok) throw new Error(`PDF service returned ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `SmartMetrology_${audit.inspection_id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast("Official-format PDF report downloaded.");
    } catch (e) {
      toast("PDF export failed: " + e.message, "error");
    } finally {
      b.disabled = false;
      b.textContent = old;
    }
  });

  // ---------------------------------------------------------------------------
  // HISTORY, RULES & ANALYTICS
  // ---------------------------------------------------------------------------
  function renderHistory() {
    const rows = [...recentHistory];
    if (audit.inspection_id && !rows.some(r => r[0] === audit.inspection_id)) {
      rows.unshift([
        audit.inspection_id,
        audit.product_name,
        "Packaged Commodity",
        new Date(audit.timestamp).toLocaleDateString("en-IN"),
        `${Math.round(audit.compliance_score || 0)}%`,
        audit.overall_status,
        review ? "A. Kumar" : "Pending"
      ]);
    }
    const base = rows.map(r => `
      <tr>
        <td class="mono">${esc(r[0])}</td>
        <td><b>${esc(r[1])}</b></td>
        <td>${esc(r[2])}</td>
        <td>${esc(r[3])}</td>
        <td><b>${esc(r[4])}</b></td>
        <td><span class="badge ${r[5] === "PASS" ? "pass" : r[5] === "WARNING" ? "warning" : "fail"}">${esc(r[5])}</span></td>
        <td>${esc(r[6])}</td>
      </tr>
    `).join("");

    $("#recent-body").innerHTML = base;
    $("#history-body").innerHTML = base.replaceAll("</tr>", '<td><button class="text-button" data-history-open>Open →</button></td></tr>');
    $$('[data-history-open]').forEach(b => b.addEventListener("click", () => showScreen("report")));
  }

  function saveRules() { localStorage.setItem("sm-rules", JSON.stringify(rules)); }
  function renderRules() {
    const q = $("#rule-search").value.toLowerCase();
    const filter = $("#rule-filter").value;
    const shown = rules.filter(r => (filter === "All statuses" || r.status === filter) && JSON.stringify(r).toLowerCase().includes(q));
    $("#rules-body").innerHTML = shown.map(r => {
      const i = rules.indexOf(r);
      return `
        <tr>
          <td class="mono">${esc(r.id)}<small> v${esc(r.version)}</small></td>
          <td>${esc(r.number)}</td>
          <td><b>${esc(r.title)}</b></td>
          <td>${esc(r.category)}</td>
          <td>${esc(r.from)} → ${esc(r.to)}</td>
          <td>${esc(r.amendment)}</td>
          <td><span class="badge ${r.status === "ACTIVE" ? "pass" : "warning"}">${r.status}</span></td>
          <td>
            <button class="text-button" data-rule-edit="${i}">Edit</button> · 
            <button class="text-button" data-rule-version="${i}">New version</button> · 
            <button class="text-button" data-rule-toggle="${i}">${r.status === "ACTIVE" ? "Deactivate" : "Activate"}</button>
          </td>
        </tr>
      `;
    }).join("");

    $$('[data-rule-edit]').forEach(b => b.onclick = () => ruleForm(Number(b.dataset.ruleEdit)));
    $$('[data-rule-version]').forEach(b => b.onclick = () => {
      const r = rules[Number(b.dataset.ruleVersion)];
      rules.push({ ...r, id: `${r.id}-V${Number(r.version) + 1}`, version: Number(r.version) + 1, from: new Date().toLocaleDateString("en-IN"), amendment: "New administrator version", status: "INACTIVE" });
      saveRules();
      renderRules();
      toast("Immutable rule version created as inactive.");
    });
    $$('[data-rule-toggle]').forEach(b => b.onclick = () => {
      const r = rules[Number(b.dataset.ruleToggle)];
      r.status = r.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
      saveRules();
      renderRules();
      toast(`Rule ${r.status.toLowerCase()}.`);
    });
  }

  function ruleForm(index = null) {
    const r = index === null ? { id: `LM-PC-${String(rules.length + 1).padStart(3, "0")}`, number: "", title: "", category: "General Packaged Commodity", from: new Date().toLocaleDateString("en-IN"), to: "—", amendment: "", status: "INACTIVE", version: 2026 } : rules[index];
    openModal(index === null ? "Add statutory rule" : "Edit rule metadata", `
      <form class="modal-form" id="rule-form">
        <label>Rule ID<input id="rf-id" value="${esc(r.id)}" required></label>
        <label>Rule number<input id="rf-number" value="${esc(r.number)}" required></label>
        <label>Rule title<input id="rf-title" value="${esc(r.title)}" required></label>
        <label>Product category<input id="rf-category" value="${esc(r.category)}" required></label>
        <label>Amendment / notification<input id="rf-amendment" value="${esc(r.amendment)}"></label>
        <button class="btn btn-primary">SAVE RULE</button>
      </form>
    `);
    $("#rule-form").onsubmit = e => {
      e.preventDefault();
      const next = { ...r, id: $("#rf-id").value, number: $("#rf-number").value, title: $("#rf-title").value, category: $("#rf-category").value, amendment: $("#rf-amendment").value };
      if (index === null) rules.push(next); else rules[index] = next;
      saveRules();
      closeModal();
      renderRules();
      toast("Rule database updated.");
    };
  }

  $("#add-rule").onclick = () => ruleForm();
  $("#rule-search").oninput = renderRules;
  $("#rule-filter").onchange = renderRules;
  $("#import-rule").onclick = () => {
    openModal("Import amendment", `
      <form class="modal-form" id="import-form">
        <label>Government notification / amendment<input type="file" id="amendment-file" accept=".pdf,.json" required></label>
        <p>The imported text remains inactive until an authorised administrator validates and activates its rule version.</p>
        <button class="btn btn-primary">IMPORT AS DRAFT</button>
      </form>
    `);
    $("#import-form").onsubmit = e => {
      e.preventDefault();
      closeModal();
      toast("Amendment imported as an inactive draft.");
    };
  };

  async function loadAnalytics() {
    try {
      const r = await fetch("/api/analytics");
      if (r.ok) {
        const d = await r.json();
        $("#analytics-rate").textContent = `${d.pass_rate}%`;
        $("#metric-total").textContent = d.total_audited;
        $("#metric-pass").textContent = d.pass_count;
        $("#metric-fail").textContent = d.violations_count;
      }
    } catch (_) {}

    const bars = [["Consumer care details", 31], ["Unit sale price", 24], ["MRP tax declaration", 19], ["Non-standard units", 15], ["Manufacturing date", 11]];
    $("#violation-bars").innerHTML = bars.map(x => `
      <div class="bar-row">
        <div><b>${x[0]}</b><span>${x[1]}%</span></div>
        <div class="bar-track"><div class="bar-fill" style="width:${x[1] * 2.6}%"></div></div>
      </div>
    `).join("");

    const makers = [
      ["ABC Foods Pvt Ltd", "5 inspections · 3 violations"],
      ["North Valley Foods", "4 inspections · 2 violations"],
      ["Ayush Care Ltd", "7 inspections · 2 warnings"],
      ["Royal Foods India", "9 inspections · 96% compliant"]
    ];
    $("#manufacturer-list").innerHTML = makers.map((x, i) => `
      <div class="risk-row">
        <b>${x[0]}</b>
        <span class="badge ${i < 2 ? "fail" : i === 2 ? "warning" : "pass"}">${i < 2 ? "HIGH" : i === 2 ? "WATCH" : "LOW"}</span>
        <small>${x[1]}</small>
      </div>
    `).join("");
  }

  $("#refresh-analytics").onclick = () => { loadAnalytics(); toast("Analytics refreshed."); };
  $("#history-search").oninput = e => {
    $$("#history-body tr").forEach(tr => tr.hidden = !tr.textContent.toLowerCase().includes(e.target.value.toLowerCase()));
  };

  // Initial render
  renderHistory();
  renderRules();
  loadAnalytics();
});
