const CACHE='smartmetrology-v4-shell';
const SHELL=['/','/static/style.css','/static/script.js','/static/immersive.js','/static/v4_ui.js','/static/manifest.webmanifest'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).catch(()=>{}));self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET')return;
  event.respondWith(fetch(req).then(res=>{const copy=res.clone();caches.open(CACHE).then(cache=>cache.put(req,copy)).catch(()=>{});return res;}).catch(()=>caches.match(req).then(hit=>hit||caches.match('/'))));
});
