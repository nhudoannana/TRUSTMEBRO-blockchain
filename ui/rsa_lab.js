/* RSA1 runs on the backend; each input revision owns its response. */
(() => {
  const $ = id => document.getElementById(id);
  const base = '/api/labs/rsa';
  const channel = () => ({token:0, busy:false, result:null});
  const fresh = () => ({keys:{A:null,B:null}, creating:channel(), encrypt:channel(), decrypt:channel(), saved:null});
  let owner = fresh(), ttlTimer;
  async function request(path, method='POST', body) {
    const controller = new AbortController();
    let timedOut=false, timer;
    const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{
      timedOut=true;controller.abort();reject(new Error('Hết thời gian chờ backend; bạn có thể tự thử lại.'));
    },15000);});
    const work=(async()=>{
      const response = await fetch(base+path, {method, credentials:'same-origin', signal:controller.signal,
        headers:body===undefined?{}:{'Content-Type':'application/json'}, ...(body===undefined?{}:{body:JSON.stringify(body)})});
      const data = await response.json();
      if(timedOut) {
        if(path==='/keys' && method==='POST' && response.ok && data.key_handle)clearKey(data.key_handle).catch(()=>{});
        throw new Error('Response đã hết hạn.');
      }
      if (!response.ok) {
        const error = new Error(Array.isArray(data.detail)?data.detail.map(e=>e.msg).join('; '):data.detail?.message||'Không thực hiện được: HTTP '+response.status);
        error.status=response.status; throw error;
      }
      return data;
    })();
    try { return await Promise.race([work,deadline]); }
    finally { clearTimeout(timer); }
  }
  const clearKey = handle => request('/keys/'+encodeURIComponent(handle),'DELETE');
  function error(message='') { $('rsa-error').textContent=message; $('rsa-error').hidden=!message; }
  function changed(name) {
    const c=owner[name]; ++c.token; c.busy=false; c.result=null;
    error(); render();
  }
  function useKey(role) {
    const key=owner.keys[role]; if(!key)return;
    $('rsa-public-key').value=key.public_key_pem; changed('encrypt');
    $('rsa-status').textContent='Đã chọn public key '+role+'; bấm Mã hóa để xử lý input hiện tại.';
  }
  async function createKey(role) {
    const o=owner,c=o.creating;if(c.busy)return;
    const token=++c.token;c.busy=true;error();render();
    $('rsa-status').textContent='Backend đang tạo khóa '+role+'; khóa cũ được giữ đến khi tạo mới thành công.';
    try {
      const data=await request('/keys','POST',{purpose:'oaep'});
      if(owner!==o || c.token!==token) { await clearKey(data.key_handle).catch(()=>{});return; }
      const old=o.keys[role];
      o.keys[role]={...data,expiresAt:Date.now()+data.expires_in_seconds*1000};
      if($('rsa-decrypt-key').value===role)changed('decrypt');
      if(!$('rsa-public-key').value)useKey(role);
      $('rsa-status').textContent='Đã tạo khóa '+role+' trên backend. Dùng nút chọn public key; bản mã đang giữ không bị thay.';
      render();
      if(old) {
        try { await clearKey(old.key_handle); }
        catch { if(owner===o && c.token===token)error('Khóa mới đã tạo; chưa xác nhận dọn khóa cũ. Khóa cũ sẽ hết hạn, không tự tạo lại.'); }
      }
    } catch(e) {
      if(owner===o && c.token===token)error('Không tạo được khóa mới; khóa '+role+' cũ được giữ. '+e.message);
    } finally { if(owner===o && c.token===token){c.busy=false;render();} }
  }
  async function cryptoAction(name, event) {
    event?.preventDefault();
    const o=owner,c=o[name];if(c.busy)return;
    const role=$('rsa-decrypt-key').value,key=o.keys[role];
    if(name==='decrypt' && !key){error('Tạo khóa riêng '+role+' trước khi giải mã.');return;}
    const body=name==='encrypt'?{message:$('rsa-message').value,public_key_pem:$('rsa-public-key').value}:
      {key_handle:key.key_handle,ciphertext_b64:$('rsa-ciphertext').value};
    const token=++c.token;c.busy=true;c.result=null;error();render();
    $('rsa-status').textContent='Đang chờ backend '+(name==='encrypt'?'mã hóa':'giải mã')+'; sửa input sẽ bỏ lượt chờ trên giao diện.';
    try {
      const result=await request('/'+name,'POST',body);
      if(owner!==o || c.token!==token)return;
      c.result={...result,submitted:body};
      $('rsa-status').textContent='Đã nhận kết quả cho đúng input đã gửi; đọc outcome, không chỉ HTTP 200.';
    } catch(e) {
      if(owner!==o || c.token!==token)return;
      if(e.status===404 && name==='decrypt' && o.keys[role]?.key_handle===body.key_handle)o.keys[role]=null;
      error((e.status===422?'Lỗi định dạng/giới hạn; chưa thực hiện phép tính. ':e.status===404?'Khóa riêng không khả dụng; public key đang giữ vẫn là dữ liệu công khai. ':'Lỗi vận hành; chưa có kết quả đáng tin. ')+e.message);
    } finally { if(owner===o && c.token===token){c.busy=false;render();} }
  }
  function keep() {
    const result=owner.encrypt.result;if(!result)return;
    owner.saved=result;render();$('rsa-status').textContent='Đã giữ một bản mã A cùng input/key đã mã hóa; mã hóa tiếp không thay mốc này.';
  }
  function loadSaved() {
    if(!owner.saved)return;
    $('rsa-ciphertext').value=owner.saved.ciphertext_b64;changed('decrypt');
    $('rsa-status').textContent='Đã chép bản mã đang giữ; tự chọn private key A/B và bấm Giải mã.';
  }
  function loadCurrent() {
    if(!owner.encrypt.result)return;
    $('rsa-ciphertext').value=owner.encrypt.result.ciphertext_b64;changed('decrypt');
  }
  function bytes() {
    $('rsa-byte-count').textContent=new TextEncoder().encode($('rsa-message').value).length+' / 190 byte UTF-8';
  }
  function render() {
    const o=owner;
    clearTimeout(ttlTimer);
    for(const role of ['A','B']) {
      const k=o.keys[role];
      $('rsa-fingerprint-'+role.toLowerCase()).value=k?k.public_key_fingerprint:'';
      $('rsa-create-'+role.toLowerCase()).disabled=o.creating.busy;
      $('rsa-use-'+role.toLowerCase()).disabled=!k;
      $('rsa-key-'+role.toLowerCase()).textContent=k?'Khóa '+role+' · RSA-2048 · e=65537\nFingerprint SPKI: '+k.public_key_fingerprint+'\nThời gian còn lại (xấp xỉ): '+Math.max(0,Math.ceil((k.expiresAt-Date.now())/1000))+'s (không gia hạn)\n'+k.public_key_pem:'Chưa có khóa '+role+'.';
    }
    $('rsa-encrypt').disabled=o.encrypt.busy;
    $('rsa-decrypt').disabled=o.decrypt.busy || !o.keys[$('rsa-decrypt-key').value];
    $('rsa-keep').disabled=!o.encrypt.result;
    $('rsa-load-current').disabled=!o.encrypt.result;
    $('rsa-load-saved').disabled=!o.saved;
    const r=o.encrypt.result;
    $('rsa-encrypt-result').hidden=!r;
    $('rsa-encrypt-result').textContent=r?'Đã mã hóa · '+r.message_utf8_bytes+' byte UTF-8\nVăn bản đã gửi: '+JSON.stringify(r.message)+'\nPublic fingerprint: '+r.public_key_fingerprint+'\nOAEP SHA-256 / MGF1 SHA-256 / label rỗng\n'+r.ciphertext_b64:'';
    $('rsa-saved').hidden=!o.saved;
    $('rsa-saved').textContent=o.saved?'Bản mã A đang giữ · '+o.saved.message_utf8_bytes+' byte\nVăn bản: '+JSON.stringify(o.saved.message)+'\nFingerprint: '+o.saved.public_key_fingerprint+'\n'+o.saved.ciphertext_b64:'';
    const d=o.decrypt.result, box=$('rsa-decrypt-result');
    box.hidden=!d;box.className='result rsa-data';
    if(d) {
      const success=d.outcome.code==='decrypted' && d.decrypted===true;
      box.className+=' '+(success?'valid':d.outcome.code==='decryption_failed'?'invalid':'warning');
      box.textContent=success?'Giải mã thành công · '+d.plaintext_utf8_bytes+' byte UTF-8\nPlaintext: '+JSON.stringify(d.plaintext)+'\nPrivate-key fingerprint: '+d.public_key_fingerprint:
        d.outcome.code==='plaintext_not_utf8'?'OAEP giải mã được byte, nhưng không phải văn bản UTF-8; lab không hiển thị dạng binary.':
        'Không giải mã được · '+d.outcome.message;
      box.textContent+='\nCiphertext đã gửi: '+d.submitted.ciphertext_b64;
    } else box.textContent='';
    bytes();
    if(Object.values(o.keys).some(k=>k && k.expiresAt>Date.now()))ttlTimer=setTimeout(render,1000);
  }
  async function reset() {
    const old=owner,next=fresh();owner=next;
    ['rsa-message','rsa-public-key','rsa-ciphertext'].forEach(id=>$(id).value='');
    $('rsa-decrypt-key').value='A';error();render();
    $('rsa-status').textContent='Đã reset riêng RSA; đang dọn các private handle đã biết.';
    try {
      await Promise.all(Object.values(old.keys).filter(Boolean).map(k=>clearKey(k.key_handle)));
      if(owner===next)$('rsa-status').textContent='Đã reset RSA và dọn các handle đã biết. Lab khác và journey không đổi.';
    } catch {
      if(owner===next)error('Đã reset cục bộ; chưa xác nhận dọn khóa trên backend. TTL/lazy cleanup là dự phòng.');
    }
  }
  function leave() {
    const old=owner;owner=fresh();error();
    ['rsa-message','rsa-public-key','rsa-ciphertext'].forEach(id=>$(id).value='');
    render();
    $('rsa-status').textContent='Đã rời trang; tạo khóa RSA mới để tiếp tục. Không khôi phục loading/kết quả cũ.';
    Object.values(old.keys).filter(Boolean).forEach(k=>fetch(base+'/keys/'+encodeURIComponent(k.key_handle),{method:'DELETE',credentials:'same-origin',keepalive:true}).catch(()=>{}));
  }
  // Bind RSA1.
  $('rsa-create-a').onclick=()=>createKey('A');$('rsa-create-b').onclick=()=>createKey('B');
  $('rsa-use-a').onclick=()=>useKey('A');$('rsa-use-b').onclick=()=>useKey('B');
  $('rsa-encrypt-form').onsubmit=e=>cryptoAction('encrypt',e);
  $('rsa-decrypt-form').onsubmit=e=>cryptoAction('decrypt',e);
  ['rsa-message','rsa-public-key'].forEach(id=>$(id).oninput=()=>changed('encrypt'));
  $('rsa-ciphertext').oninput=()=>changed('decrypt');$('rsa-decrypt-key').onchange=()=>changed('decrypt');
  $('rsa-keep').onclick=keep;$('rsa-load-saved').onclick=loadSaved;$('rsa-load-current').onclick=loadCurrent;
  $('rsa-reset').onclick=reset;
  const samples={empty:'',text:'TrustMeBro',unicode:'  Hồ sơ\n你好 🌏  ',boundary:'a'.repeat(190)};
  for(const [name,text] of Object.entries(samples))$('rsa-sample-'+name).onclick=()=>{
    if($('rsa-message').value && !window.confirm('Thay input bằng mẫu? Chỉ điền dữ liệu, không mã hóa.'))return;
    $('rsa-message').value=text;changed('encrypt');
  };
  window.addEventListener('pagehide',leave);
  render();
})();

// RSA2 owner.
(() => {
  const $=id=>document.getElementById(id),base='/api/labs/rsa';
  const channel=()=>({token:0,busy:false,result:null});
  const fresh=()=>({keys:{A:null,B:null},creating:channel(),sign:channel(),verify:channel(),saved:null});
  let owner=fresh(),ttlTimer;
  async function request(path, method='POST', body) {
    const controller = new AbortController();
    let timedOut=false, timer;
    const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{
      timedOut=true;controller.abort();reject(new Error('Hết thời gian chờ backend; bạn có thể tự thử lại.'));
    },15000);});
    const work=(async()=>{
      const response = await fetch(base+path, {method, credentials:'same-origin', signal:controller.signal,
        headers:body===undefined?{}:{'Content-Type':'application/json'}, ...(body===undefined?{}:{body:JSON.stringify(body)})});
      const data = await response.json();
      if(timedOut) {
        if(path==='/keys' && method==='POST' && response.ok && data.key_handle)clearKey(data.key_handle).catch(()=>{});
        throw new Error('Response đã hết hạn.');
      }
      if (!response.ok) {
        const error = new Error(Array.isArray(data.detail)?data.detail.map(e=>e.msg).join('; '):data.detail?.message||'Không thực hiện được: HTTP '+response.status);
        error.status=response.status; throw error;
      }
      return data;
    })();
    try { return await Promise.race([work,deadline]); }
    finally { clearTimeout(timer); }
  }
  const clearKey=handle=>request('/keys/'+encodeURIComponent(handle),'DELETE');
  function error(message=''){$('pss-error').textContent=message;$('pss-error').hidden=!message;}
  function changed(name){const c=owner[name];++c.token;c.busy=false;c.result=null;error();render();}
  function usePublic(role){
    const k=owner.keys[role];if(!k)return;
    $('pss-verify-public-key').value=k.public_key_pem;changed('verify');
    $('pss-status').textContent='\u0110\u00e3 ch\u1ecdn public key '+role+'; n\u1ed9i dung/ch\u1eef k\u00fd draft kh\u00f4ng \u0111\u1ed5i.';
  }
  async function createKey(role){
    const o=owner,c=o.creating;if(c.busy)return;
    const token=++c.token;c.busy=true;error();render();
    $('pss-status').textContent='Backend \u0111ang t\u1ea1o kh\u00f3a PSS '+role+'; gi\u1eef kh\u00f3a c\u0169 cho \u0111\u1ebfn khi th\u00e0nh c\u00f4ng.';
    try{
      const data=await request('/keys','POST',{purpose:'pss'});
      if(owner!==o||c.token!==token){await clearKey(data.key_handle).catch(()=>{});return;}
      const old=o.keys[role];o.keys[role]={...data,expiresAt:Date.now()+data.expires_in_seconds*1000};
      if($('pss-sign-key').value===role)changed('sign');
      $('pss-status').textContent='\u0110\u00e3 t\u1ea1o kh\u00f3a PSS '+role+'; public draft v\u00e0 b\u1ea3n A \u0111ang gi\u1eef kh\u00f4ng b\u1ecb thay.';
      render();
      if(old)try{await clearKey(old.key_handle);}catch{if(owner===o&&c.token===token)error('Kh\u00f3a m\u1edbi \u0111\u00e3 t\u1ea1o; ch\u01b0a x\u00e1c nh\u1eadn d\u1ecdn kh\u00f3a c\u0169. TTL/session cleanup l\u00e0 d\u1ef1 ph\u00f2ng.');}
    }catch(e){if(owner===o&&c.token===token)error('Kh\u00f4ng t\u1ea1o \u0111\u01b0\u1ee3c kh\u00f3a m\u1edbi; gi\u1eef kh\u00f3a '+role+' c\u0169. '+e.message);}
    finally{if(owner===o&&c.token===token){c.busy=false;render();}}
  }
  async function removeKey(role){
    const o=owner,c=o.creating,k=o.keys[role];if(c.busy||!k)return;
    const token=++c.token;c.busy=true;error();render();
    try{
      await clearKey(k.key_handle);
      if(owner!==o||c.token!==token)return;
      o.keys[role]=null;if($('pss-sign-key').value===role)changed('sign');
      $('pss-status').textContent='\u0110\u00e3 x\u00f3a private handle '+role+'. Public draft/b\u1ea3n A v\u1eabn x\u00e1c minh \u0111\u01b0\u1ee3c; kh\u00f4ng coi ch\u1eef k\u00fd l\u00e0 b\u1ecb thu h\u1ed3i.';
    }catch(e){
      if(owner===o&&c.token===token){
        if(e.status===404){o.keys[role]=null;if($('pss-sign-key').value===role)changed('sign');}
        error((e.status===404?'Private handle kh\u00f4ng kh\u1ea3 d\u1ee5ng; public verification v\u1eabn d\u00f9ng \u0111\u01b0\u1ee3c. ':'Ch\u01b0a x\u00e1c nh\u1eadn x\u00f3a private handle. ')+e.message);
      }
    }
    finally{if(owner===o&&c.token===token){c.busy=false;render();}}
  }
  async function action(name,event){
    event?.preventDefault();const o=owner,c=o[name];if(c.busy)return;
    const role=$('pss-sign-key').value,k=o.keys[role];
    if(name==='sign'&&!k){error('T\u1ea1o private key PSS '+role+' tr\u01b0\u1edbc khi k\u00fd.');return;}
    const body=name==='sign'?{key_handle:k.key_handle,message:$('pss-message').value}:
      {message:$('pss-verify-message').value,signature_b64:$('pss-signature').value,public_key_pem:$('pss-verify-public-key').value};
    const token=++c.token;c.busy=true;c.result=null;error();render();
    $('pss-status').textContent='\u0110ang ch\u1edd backend '+(name==='sign'?'k\u00fd':'x\u00e1c minh')+'; s\u1eeda input cho ph\u00e9p t\u1ef1 retry.';
    try{
      const result=await request('/'+name,'POST',body);
      if(owner!==o||c.token!==token)return;
      c.result={...result,submitted:body};$('pss-status').textContent='\u0110\u00e3 nh\u1eadn k\u1ebft qu\u1ea3 cho input \u0111\u00e3 g\u1eedi; \u0111\u1ecdc outcome, kh\u00f4ng ch\u1ec9 HTTP 200.';
    }catch(e){
      if(owner!==o||c.token!==token)return;
      if(name==='sign'&&e.status===404&&o.keys[role]?.key_handle===body.key_handle)o.keys[role]=null;
      error((e.status===422?'L\u1ed7i \u0111\u1ecbnh d\u1ea1ng/gi\u1edbi h\u1ea1n; ch\u01b0a c\u00f3 k\u1ebft qu\u1ea3 crypto. ':e.status===404?'Private key kh\u00f4ng kh\u1ea3 d\u1ee5ng; public verification v\u1eabn d\u00f9ng \u0111\u01b0\u1ee3c. ':e.status===409?'C\u1ea7n \u0111\u00fang kh\u00f3a purpose PSS. ':'L\u1ed7i v\u1eadn h\u00e0nh; kh\u00f4ng k\u1ebft lu\u1eadn ch\u1eef k\u00fd sai. ')+e.message);
    }finally{if(owner===o&&c.token===token){c.busy=false;render();}}
  }
  function keep(){
    if(!owner.sign.result)return;owner.saved=owner.sign.result;render();
    $('pss-status').textContent='\u0110\u00e3 gi\u1eef m\u1ed9t b\u1ea3n A v\u1edbi \u0111\u00fang text/hash/public key/ch\u1eef k\u00fd. Draft v\u00e0 l\u1ea7n k\u00fd sau kh\u00f4ng thay m\u1ed1c n\u00e0y.';
  }
  function load(result){
    if(!result)return;
    $('pss-verify-message').value=result.message;$('pss-signature').value=result.signature_b64;
    $('pss-verify-public-key').value=result.public_key_pem;changed('verify');
    $('pss-status').textContent='\u0110\u00e3 ch\u00e9p text, ch\u1eef k\u00fd v\u00e0 public key sang draft; b\u1ea5m X\u00e1c minh.';
  }
  function loadCurrent(){load(owner.sign.result);}
  function loadSaved(){load(owner.saved);}
  function artifact(r){return r?'N\u1ed9i dung \u0111\u00e3 k\u00fd: '+JSON.stringify(r.message)+'\n'+r.message_utf8_bytes+' byte UTF-8\nSHA-256: '+r.message_sha256+'\nPublic fingerprint: '+r.public_key_fingerprint+'\nPSS SHA-256 / MGF1 SHA-256 / salt 32 byte\n'+r.signature_b64+'\n'+r.public_key_pem:'';}
  function render(){
    const o=owner;clearTimeout(ttlTimer);
    for(const role of ['A','B']){
      const k=o.keys[role],id=role.toLowerCase();
      $('pss-create-'+id).disabled=o.creating.busy;$('pss-delete-'+id).disabled=o.creating.busy||!k;$('pss-use-'+id).disabled=!k;
      $('pss-fingerprint-'+id).value=k?k.public_key_fingerprint:'';
      $('pss-key-'+id).textContent=k?'PSS '+role+' \u00b7 RSA-2048/e65537\nFingerprint: '+k.public_key_fingerprint+'\nTTL c\u00f2n l\u1ea1i (x\u1ea5p x\u1ec9): '+Math.max(0,Math.ceil((k.expiresAt-Date.now())/1000))+'s\n'+k.public_key_pem:'Ch\u01b0a c\u00f3 kh\u00f3a PSS '+role+'.';
    }
    $('pss-sign').disabled=o.sign.busy||!o.keys[$('pss-sign-key').value];$('pss-verify').disabled=o.verify.busy;
    $('pss-keep').disabled=!o.sign.result;$('pss-load-current').disabled=!o.sign.result;$('pss-load-saved').disabled=!o.saved;
    $('pss-sign-result').hidden=!o.sign.result;$('pss-sign-result').textContent=artifact(o.sign.result);
    $('pss-saved').hidden=!o.saved;$('pss-saved').textContent=o.saved?'B\u1ea3n A \u0111ang gi\u1eef\n'+artifact(o.saved):'';
    $('pss-sign-hash').value=o.sign.result?.message_sha256||'';
    const r=o.verify.result,box=$('pss-verify-result');box.hidden=!r;box.className='result rsa-data';
    $('pss-verify-hash').value=r?.message_sha256||'';
    if(r){
      const valid=r.valid===true&&r.outcome.code==='signature_valid';box.className+=' '+(valid?'valid':'invalid');
      box.textContent=(valid?'Ch\u1eef k\u00fd h\u1ee3p l\u1ec7 v\u1edbi public key \u0111\u00e3 ch\u1ecdn.':'Ch\u1eef k\u00fd kh\u00f4ng kh\u1edbp text/key/tham s\u1ed1; kh\u00f4ng x\u00e1c \u0111\u1ecbnh ai \u0111\u00e3 s\u1eeda.')+
        '\nN\u1ed9i dung \u0111\u00e3 x\u00e1c minh: '+JSON.stringify(r.message)+'\n'+r.message_utf8_bytes+' byte UTF-8\nSHA-256: '+r.message_sha256+
        '\nPublic fingerprint: '+r.public_key_fingerprint+'\nPSS SHA-256 / MGF1 SHA-256 / salt 32 byte\nCh\u1eef k\u00fd \u0111\u00e3 g\u1eedi: '+r.submitted.signature_b64+
        '\nH\u1ee3p l\u1ec7 kh\u00f4ng ch\u1ee9ng minh n\u1ed9i dung \u0111\u00fang ho\u1eb7c danh t\u00ednh ngo\u00e0i \u0111\u1eddi.';
    }else box.textContent='';
    $('pss-byte-count').textContent=new TextEncoder().encode($('pss-message').value).length+' / 4096 byte UTF-8';
    $('pss-verify-byte-count').textContent=new TextEncoder().encode($('pss-verify-message').value).length+' / 4096 byte UTF-8';
    if(Object.values(o.keys).some(k=>k&&k.expiresAt>Date.now()))ttlTimer=setTimeout(render,1000);
  }
  function clearInputs(){['pss-message','pss-verify-message','pss-verify-public-key','pss-signature','pss-prediction'].forEach(id=>$(id).value='');$('pss-sign-key').value='A';}
  async function reset(){
    const old=owner,next=fresh();owner=next;clearInputs();error();render();
    $('pss-status').textContent='\u0110\u00e3 reset ri\u00eang PSS; \u0111ang d\u1ecdn handles \u0111\u00e3 bi\u1ebft.';
    try{await Promise.all(Object.values(old.keys).filter(Boolean).map(k=>clearKey(k.key_handle)));if(owner===next)$('pss-status').textContent='\u0110\u00e3 reset PSS v\u00e0 d\u1ecdn handles \u0111\u00e3 bi\u1ebft. OAEP/lab kh\u00e1c/journey kh\u00f4ng \u0111\u1ed5i.';}
    catch{if(owner===next)error('\u0110\u00e3 reset c\u1ee5c b\u1ed9; ch\u01b0a x\u00e1c nh\u1eadn d\u1ecdn backend. TTL/session cleanup l\u00e0 d\u1ef1 ph\u00f2ng.');}
  }
  function leave(){
    const old=owner;owner=fresh();clearInputs();error();render();
    $('pss-status').textContent='\u0110\u00e3 r\u1eddi trang; t\u1ea1o private handle m\u1edbi \u0111\u1ec3 k\u00fd. Kh\u00f4ng kh\u00f4i ph\u1ee5c loading/k\u1ebft qu\u1ea3 c\u0169.';
    Object.values(old.keys).filter(Boolean).forEach(k=>fetch(base+'/keys/'+encodeURIComponent(k.key_handle),{method:'DELETE',credentials:'same-origin',keepalive:true}).catch(()=>{}));
  }
  // Bind RSA2.
  for(const role of ['A','B']){
    const id=role.toLowerCase();$('pss-create-'+id).onclick=()=>createKey(role);$('pss-delete-'+id).onclick=()=>removeKey(role);$('pss-use-'+id).onclick=()=>usePublic(role);
  }
  $('pss-sign-form').onsubmit=e=>action('sign',e);$('pss-verify-form').onsubmit=e=>action('verify',e);
  $('pss-message').oninput=()=>changed('sign');$('pss-sign-key').onchange=()=>changed('sign');
  ['pss-verify-message','pss-verify-public-key','pss-signature'].forEach(id=>$(id).oninput=()=>changed('verify'));
  $('pss-keep').onclick=keep;$('pss-load-current').onclick=loadCurrent;$('pss-load-saved').onclick=loadSaved;$('pss-reset').onclick=reset;
  for(const [name,text] of Object.entries({empty:'',text:'TrustMeBro',unicode:'  H\u1ed3 s\u01a1\n\u4f60\u597d \ud83c\udf0f  ',boundary:'a'.repeat(4096)}))$('pss-sample-'+name).onclick=()=>{
    if($('pss-message').value&&!window.confirm('Thay input b\u1eb1ng m\u1eabu? Ch\u1ec9 \u0111i\u1ec1n, kh\u00f4ng t\u1ef1 k\u00fd.'))return;
    $('pss-message').value=text;changed('sign');
  };
  window.addEventListener('pagehide',leave);render();
})();
