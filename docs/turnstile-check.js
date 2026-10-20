let loading;
function loadTurnstile(){
 if(window.turnstile?.render)return Promise.resolve(window.turnstile);
 if(loading)return loading;
 loading=new Promise((resolve,reject)=>{
  const script=document.createElement('script');const timer=setTimeout(fail,15000);
  function fail(){clearTimeout(timer);script.remove();delete window.cryptoCropsTurnstileReady;loading=null;reject(Error('The security check could not load. Please refresh and try again.'));}
  window.cryptoCropsTurnstileReady=()=>{clearTimeout(timer);delete window.cryptoCropsTurnstileReady;resolve(window.turnstile);};
  script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?onload=cryptoCropsTurnstileReady&render=explicit';script.async=true;script.defer=true;script.onerror=fail;document.head.append(script);
 });return loading;
}
export async function mountTurnstile(container,config,callbacks={}){
 const api=await loadTurnstile();let alive=true;
 const current=()=>alive&&container.isConnected&&(callbacks.isCurrent?.()??true);if(!current())return null;
 const element=document.createElement('div');element.className='turnstile-widget';container.replaceChildren(element);
 const id=api.render(element,{sitekey:config.site_key,action:config.action,cData:config.cdata,theme:'light',size:container.getBoundingClientRect().width<310?'compact':'normal','refresh-expired':'manual',
  callback(token){if(current())callbacks.onToken?.(token);},
  'expired-callback'(){if(current()){callbacks.onToken?.('');callbacks.onExpired?.();}},
  'error-callback'(){if(current()){callbacks.onToken?.('');callbacks.onState?.('error');}},
 });
 return {element,destroy(){alive=false;try{api.remove(id);}catch{}element.remove();}};
}
