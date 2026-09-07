document.addEventListener("DOMContentLoaded",()=>{
  const login=document.querySelector("#inspector-login");
  if(!login)return;
  const visual=login.querySelector(".login-visual");
  const copy=login.querySelector(".login-copy");
  const card=login.querySelector(".login-card");
  const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if(visual&&!visual.querySelector(".login-particles")){
    const particles=document.createElement("div");
    particles.className="login-particles";
    for(let i=0;i<26;i++){
      const p=document.createElement("span");
      p.className="login-particle";
      p.style.left=`${Math.round(Math.random()*100)}%`;
      p.style.setProperty("--dur",`${7+Math.random()*8}s`);
      p.style.setProperty("--delay",`${-Math.random()*12}s`);
      p.style.setProperty("--drift",`${-50+Math.random()*100}px`);
      particles.appendChild(p);
    }
    visual.appendChild(particles);

    const core=document.createElement("div");
    core.className="login-core";
    core.innerHTML="<span></span><span></span><span></span>";
    visual.appendChild(core);
  }

  if(reduced||window.innerWidth<901)return;

  login.addEventListener("pointermove",e=>{
    const x=e.clientX/window.innerWidth;
    const y=e.clientY/window.innerHeight;
    login.style.setProperty("--login-x",`${x*100}%`);
    login.style.setProperty("--login-y",`${y*100}%`);
    if(copy){
      copy.style.transform=`perspective(1000px) rotateX(${(0.5-y)*4}deg) rotateY(${(x-0.5)*5}deg) translateZ(22px)`;
    }
  },{passive:true});

  if(card){
    card.addEventListener("pointermove",e=>{
      const r=card.getBoundingClientRect();
      const x=(e.clientX-r.left)/r.width-.5;
      const y=(e.clientY-r.top)/r.height-.5;
      card.style.transform=`perspective(1100px) rotateX(${(-y*4.5).toFixed(2)}deg) rotateY(${(x*5.5).toFixed(2)}deg) translateY(-2px)`;
    });
    card.addEventListener("pointerleave",()=>{
      card.style.transform="perspective(1100px) rotateX(0deg) rotateY(0deg) translateY(0)";
    });
  }
});
