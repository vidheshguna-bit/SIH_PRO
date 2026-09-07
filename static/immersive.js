document.addEventListener("DOMContentLoaded",()=>{
  const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ambient=document.createElement("div");
  ambient.className="ambient-video";
  ambient.setAttribute("aria-hidden","true");
  ambient.innerHTML='<span class="orb one"></span><span class="orb two"></span><span class="orb three"></span><span class="scan-line"></span>';
  document.body.prepend(ambient);

  const login=document.createElement("section");
  login.className="inspector-login";
  login.id="inspector-login";
  login.innerHTML=`
    <div class="login-visual" aria-hidden="true">
      <div class="login-grid"></div><div class="login-ring r1"></div><div class="login-ring r2"></div>
      <div class="login-copy"><span>SMARTMETROLOGY AI · SIH26034</span><h1>Legal Metrology<br>Inspection Intelligence</h1><p>Explainable AI assistance with deterministic statutory validation.</p><div class="login-flow"><b>SCAN</b><i>→</i><b>EXTRACT</b><i>→</i><b>VALIDATE</b><i>→</i><b>REVIEW</b></div></div>
    </div>
    <div class="login-side"><form class="login-card" id="inspector-login-form">
      <div class="login-brand"><div class="brand-mark">SM</div><div><strong>SmartMetrology AI</strong><span>Inspector Secure Access</span></div></div>
      <span class="eyebrow">AUTHORISED PERSONNEL ONLY</span><h2>Inspector Sign In</h2><p>Enter your inspector credentials to access the compliance workspace.</p>
      <label>Inspector ID<input id="inspector-id" autocomplete="username" placeholder="e.g. LM-INS-2026" required></label>
      <label>Password<div class="password-wrap"><input id="inspector-password" type="password" autocomplete="current-password" placeholder="Enter password" required><button type="button" id="toggle-password" aria-label="Show password">◉</button></div></label>
      <div class="login-options"><label><input type="checkbox" id="remember-inspector"> Remember Inspector ID</label><button type="button" id="login-help">Need access help?</button></div>
      <button class="btn btn-primary login-submit" type="submit">SIGN IN TO INSPECTOR PORTAL →</button>
      <div class="demo-credentials"><b>SIH prototype access</b><span>ID: LM-INS-2026</span><span>Password: Smart@26034</span></div>
      <small class="security-note">🔒 Prototype authentication for SIH demonstration. Production deployments should use a server-side identity provider.</small>
      <div class="login-error" id="login-error" role="alert"></div>
    </form></div>`;
  document.body.append(login);

  const appShell=document.querySelector(".app-shell");
  const sidebar=document.querySelector(".sidebar");
  const storedId=localStorage.getItem("sm-inspector-id")||"";
  document.querySelector("#inspector-id").value=storedId;
  document.querySelector("#remember-inspector").checked=!!storedId;

  const setLoggedIn=(yes)=>{
    document.body.classList.toggle("login-required",!yes);
    login.classList.toggle("hidden",yes);
    if(appShell)appShell.setAttribute("aria-hidden",yes?"false":"true");
    if(sidebar)sidebar.setAttribute("aria-hidden",yes?"false":"true");
  };
  setLoggedIn(sessionStorage.getItem("sm-inspector-session")==="active");

  document.querySelector("#toggle-password").addEventListener("click",()=>{
    const input=document.querySelector("#inspector-password");
    input.type=input.type==="password"?"text":"password";
  });
  document.querySelector("#login-help").addEventListener("click",()=>{
    document.querySelector("#login-error").textContent="For the SIH prototype, use the demo credentials shown below. Production access will be issued by the department administrator.";
  });
  document.querySelector("#inspector-login-form").addEventListener("submit",e=>{
    e.preventDefault();
    const id=document.querySelector("#inspector-id").value.trim();
    const password=document.querySelector("#inspector-password").value;
    const error=document.querySelector("#login-error");
    if(id!=="LM-INS-2026"||password!=="Smart@26034"){
      error.textContent="Invalid Inspector ID or password.";
      document.querySelector(".login-card").classList.remove("shake"); void document.querySelector(".login-card").offsetWidth; document.querySelector(".login-card").classList.add("shake");
      return;
    }
    if(document.querySelector("#remember-inspector").checked)localStorage.setItem("sm-inspector-id",id); else localStorage.removeItem("sm-inspector-id");
    sessionStorage.setItem("sm-inspector-session","active");
    error.textContent=""; setLoggedIn(true);
  });

  const topActions=document.querySelector(".top-actions");
  if(topActions){
    const logout=document.createElement("button");
    logout.className="icon-button logout-button"; logout.title="Sign out"; logout.textContent="↪";
    logout.addEventListener("click",()=>{sessionStorage.removeItem("sm-inspector-session");setLoggedIn(false);document.querySelector("#inspector-password").value="";});
    topActions.prepend(logout);
  }

  const scannerPanel=document.querySelector(".scanner-panel");
  const uploadGrid=document.querySelector("#upload-grid");
  const imageInput=document.querySelector("#image-input");
  if(scannerPanel&&uploadGrid&&imageInput){
    const sourceBar=document.createElement("div");
    sourceBar.className="capture-source-bar";
    sourceBar.innerHTML='<div><b>Choose capture method</b><span>Upload existing product images or capture directly using your camera.</span></div><div class="capture-actions"><button type="button" class="btn btn-secondary" id="upload-image-action">⇧ UPLOAD IMAGE</button><button type="button" class="btn btn-primary" id="camera-action">◉ USE CAMERA</button></div>';
    uploadGrid.before(sourceBar);

    let selectedPanel=0;
    const setPanel=(index)=>{
      selectedPanel=Math.max(0,Math.min(3,Number(index)||0));
      document.querySelectorAll(".upload-slot").forEach((s,i)=>s.classList.toggle("capture-selected",i===selectedPanel));
    };
    setPanel(0);

    document.querySelectorAll(".upload-slot").forEach(slot=>{
      slot.addEventListener("click",e=>{setPanel(slot.dataset.index);},true);
    });

    document.querySelector("#upload-image-action").addEventListener("click",()=>{
      imageInput.dataset.target=String(selectedPanel); imageInput.click();
    });

    const cameraModal=document.createElement("div");
    cameraModal.className="camera-modal"; cameraModal.id="camera-modal";
    cameraModal.innerHTML=`<div class="camera-dialog"><div class="camera-head"><div><span class="eyebrow">LIVE PRODUCT CAPTURE</span><h2>Camera Scanner</h2></div><button type="button" id="close-camera">×</button></div><div class="camera-stage"><video id="camera-preview" autoplay playsinline muted></video><div class="camera-frame"><span></span><span></span><span></span><span></span><b>Align declaration panel inside frame</b></div><div class="camera-status" id="camera-status">Requesting camera permission…</div></div><div class="camera-controls"><button type="button" class="btn btn-secondary" id="switch-camera">⟳ SWITCH CAMERA</button><button type="button" class="camera-shutter" id="camera-shutter" aria-label="Capture photo"><i></i></button><button type="button" class="btn btn-secondary" id="cancel-camera">CANCEL</button></div><canvas id="camera-canvas" hidden></canvas></div>`;
    document.body.append(cameraModal);

    let stream=null, facing="environment";
    const stopCamera=()=>{if(stream){stream.getTracks().forEach(t=>t.stop());stream=null;}cameraModal.classList.remove("show");};
    const startCamera=async()=>{
      cameraModal.classList.add("show");
      const status=document.querySelector("#camera-status"); status.textContent="Requesting camera permission…";
      try{
        if(stream)stream.getTracks().forEach(t=>t.stop());
        stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:facing},width:{ideal:1920},height:{ideal:1080}},audio:false});
        document.querySelector("#camera-preview").srcObject=stream; status.textContent="Camera ready · Hold device steady";
      }catch(err){
        status.textContent=location.protocol!=="https:"&&location.hostname!=="localhost"?"Camera requires HTTPS. Open the deployed Vercel/Render HTTPS site.":"Camera access denied or unavailable. Allow camera permission in your browser and retry.";
      }
    };
    document.querySelector("#camera-action").addEventListener("click",startCamera);
    document.querySelector("#close-camera").addEventListener("click",stopCamera);
    document.querySelector("#cancel-camera").addEventListener("click",stopCamera);
    cameraModal.addEventListener("click",e=>{if(e.target===cameraModal)stopCamera();});
    document.querySelector("#switch-camera").addEventListener("click",async()=>{facing=facing==="environment"?"user":"environment";await startCamera();});
    document.querySelector("#camera-shutter").addEventListener("click",()=>{
      const video=document.querySelector("#camera-preview"); if(!stream||!video.videoWidth)return;
      const canvas=document.querySelector("#camera-canvas"); canvas.width=video.videoWidth; canvas.height=video.videoHeight; canvas.getContext("2d").drawImage(video,0,0);
      canvas.toBlob(blob=>{
        if(!blob)return;
        const file=new File([blob],`camera-panel-${selectedPanel+1}-${Date.now()}.jpg`,{type:"image/jpeg"});
        const dt=new DataTransfer(); dt.items.add(file); imageInput.dataset.target=String(selectedPanel); imageInput.files=dt.files; imageInput.dispatchEvent(new Event("change",{bubbles:true}));
        stopCamera(); setPanel(Math.min(selectedPanel+1,3));
      },"image/jpeg",.92);
    });
  }

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
