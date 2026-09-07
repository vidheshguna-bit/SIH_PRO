(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    let url = typeof input === "string" ? input : input?.url;
    if (url === "/api/audit") {
      url = "/api/v4/audit-compatible";
      input = url;
      if (!init.signal) {
        const controller = new AbortController();
        init = { ...init, signal: controller.signal };
        setTimeout(() => controller.abort("Inspection timed out"), 90000);
      }
    }
    return nativeFetch(input, init);
  };

  document.addEventListener("DOMContentLoaded", () => {
    const progress = document.querySelector("#progress-label");
    const ocr = document.querySelector("#ocr-live");
    const button = document.querySelector("#start-inspection");
    if (!button || !progress || !ocr) return;
    button.addEventListener("click", () => {
      let seconds = 0;
      const timer = setInterval(() => {
        if (!document.querySelector("#screen-processing.active")) {
          clearInterval(timer);
          return;
        }
        seconds += 1;
        if (seconds >= 6) {
          progress.textContent = `AI OCR processing · ${seconds}s`;
          if (seconds === 6) ocr.textContent = "Reading real package text with OCR…\nPlease keep this tab open.";
        }
        if (seconds >= 25) ocr.textContent = "OCR is still processing the uploaded image.\nLarge phone photos are automatically optimized for faster analysis.";
      }, 1000);
    }, { capture: true });
  });
})();
