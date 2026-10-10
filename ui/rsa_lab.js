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
