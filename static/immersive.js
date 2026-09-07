document.addEventListener("DOMContentLoaded",()=>{
  const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ambient=document.createElement("div");
  ambient.className="ambient-video";
  ambient.setAttribute("aria-hidden","true");
  ambient.innerHTML='<span class="orb one"></span><span class="orb two"></span><span class="orb three"></span><span class="scan-line"></span>';
  document.body.prepend(ambient);

  if(reduced||window.innerWidth<901)return;

  document.addEventListener("pointermove",e=>{
    const x=e.clientX/window.innerWidth;
    const y=e.clientY/window.innerHeight;
    document.documentElement.style.setProperty("--mx",`${x*100}%`);
    document.documentElement.style.setProperty("--my",`${y*100}%`);
  },{passive:true});

  const initTilt=()=>{
    document.querySelectorAll(".metric,.panel,.field-card,.upload-slot,.result-hero").forEach(el=>{
      if(el.dataset.tiltReady)return;
      el.dataset.tiltReady="1";
      el.setAttribute("data-tilt","");
      el.addEventListener("pointermove",e=>{
        const r=el.getBoundingClientRect();
        const px=(e.clientX-r.left)/r.width-.5;
        const py=(e.clientY-r.top)/r.height-.5;
        el.style.setProperty("--tilt-x",`${(-py*2.2).toFixed(2)}deg`);
        el.style.setProperty("--tilt-y",`${(px*2.8).toFixed(2)}deg`);
        el.classList.add("depth-lift");
      });
      el.addEventListener("pointerleave",()=>{
        el.classList.remove("depth-lift");
        el.style.setProperty("--tilt-x","0deg");
        el.style.setProperty("--tilt-y","0deg");
      });
    });
  };

  initTilt();
  const observer=new MutationObserver(initTilt);
  observer.observe(document.querySelector(".content")||document.body,{childList:true,subtree:true});
});
