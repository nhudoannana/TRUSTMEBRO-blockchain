/* Independent queue lab: mutation bodies are captured once; draft edits affect the next action. */
(() => {
  const $ = id => document.getElementById(id);
  const base = '/api/labs/fork';
  const fresh = () => ({snapshot:null, busy:false, uncertain:false, token:0, pendingMutation:false, notice:'Chưa tạo lab.', report:null, continuation:null});
  let owner = fresh();
  const goals = {
    E1:'Dự đoán nhánh nào được giữ khi hòa; sau đó đào trên Node-3 và giao block mới để so sánh.',
    E2:'So sánh height và work trước/sau giao nhánh ngắn, có work cao.',
    E4:'Quan sát ISSUE A mất xác nhận và được khôi phục vào mempool; đào lại A trên tip mới.',
    E5:'Giao con trước cha: orphan chưa đóng góp work; giao cha để thử lại con.',
    C1:'REVOKE rời nhánh chọn: trạng thái đã xác nhận và giao dịch đang chờ khác nhau thế nào?',
    C2:'Cả ISSUE và REVOKE rời nhánh chọn: ISSUE đang chờ có cho phép REVOKE không?',
    C3:'Cùng REVOKE vẫn trên nhánh mới: có giao dịch nào thực sự được khôi phục?'
  };
  async function request(url, method='GET', body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(url, {method, credentials:'same-origin', signal:controller.signal,
        headers:body === undefined ? {} : {'Content-Type':'application/json'},
        ...(body === undefined ? {} : {body:JSON.stringify(body)})});
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail;
        const error = Error(typeof detail === 'string' ? detail : detail?.message || JSON.stringify(detail));
        error.status=response.status; error.code=detail?.code; throw error;
      }
      return data;
    } finally { clearTimeout(timer); }
  }
  async function cleanup(handle) {
    return request(base+'/'+encodeURIComponent(handle),'DELETE');
  }
  async function read(o, token) {
    const data = await request(base+'/'+encodeURIComponent(o.snapshot.lab_handle));
    if (owner !== o || o.token !== token) return;
    o.snapshot=data; o.uncertain=false;
  }
  async function recover(o, error, token) {
    if (owner !== o || o.token !== token) return;
    if (error.status === 404) {
      o.snapshot=null; o.continuation=null; o.notice='Handle hết hạn hoặc không còn thuộc phiên. Tạo lab mới; '+error.message;
      return;
    }
    o.notice='Lỗi: '+error.message+'; không tự gửi lại thao tác.';
    if (o.snapshot && (error.code==='stale_revision' || !error.status)) {
      o.uncertain=true;
      try { await read(o,token); if(owner===o && o.token===token) o.notice+=' Đã refresh state thật; hãy kiểm tra trước khi thử lại.'; }
      catch (e) {
        if(owner!==o || o.token!==token)return;
        if(e.status===404){o.snapshot=null;o.continuation=null;}
        o.notice+=' Refresh thất bại: '+e.message+'; cần refresh hoặc tạo lại lab.';
      }
    }
  }
  async function action(path, body={}) {
    const o=owner;
    if(o.busy || (path!=='create' && (!o.snapshot || o.uncertain)))return;
    const token=++o.token; o.pendingMutation=path!=='create';
    o.busy=true; render();
    try {
      const result=await request(path==='create' ? base : base+'/'+encodeURIComponent(o.snapshot.lab_handle)+'/'+path,
        'POST',path==='create' ? {} : {...body,expected_revision:o.snapshot.revision});
      if(owner!==o || o.token!==token) {
        if(path==='create') {
          try { await cleanup(result.lab_handle); }
          catch(e) { owner.notice='Cleanup handle tạo muộn chưa xác nhận: '+e.message+'; expiry 15 phút là dự phòng.';render(); }
        }
        return;
      }
      o.snapshot=path==='create' ? result : result.snapshot;
      o.uncertain=false; o.report=path==='create' ? null : result;
      o.notice=path==='create' ? 'Đã tạo ba node riêng; chưa tự giao tin.' : result.outcome.code+' — '+result.outcome.message;
      if(path==='scenario'){
        o.continuation=result.outcome.code==='scenario_ready' ? result.continuation || null : null;
        o.scenario=body.scenario;
      }
    } catch(error) { await recover(o,error,token); }
    finally { if(owner===o && o.token===token){o.busy=false;o.pendingMutation=false;render();} }
  }
  async function refresh() {
    const o=owner;if(o.busy || !o.snapshot)return;
    const token=++o.token;
    o.busy=true;render();
    try {await read(o,token);if(owner===o && o.token===token)o.notice='Đã đọc state thật, không gửi lại mutation.';}
    catch(e){await recover(o,e,token);}
    finally{if(owner===o && o.token===token){o.busy=false;render();}}
  }
  function edit() {
    const o=owner;
    if(!o.busy || !o.pendingMutation)return;
    ++o.token;o.busy=false;o.pendingMutation=false;o.uncertain=true;o.report=null;
    o.notice='Input đã đổi; đã bỏ lượt chờ cũ trên giao diện. Backend có thể đã thực hiện. Bấm Refresh state trước khi thử lại; không tự gửi lại thao tác.';
    render();
  }
  async function reset() {
    const old=owner, next=fresh();owner=next;render();
    if(!old.snapshot){next.notice='Đã reset giao diện; handle đang tạo muộn sẽ được dọn khi nhận được.';render();return;}
    next.notice='Đang dọn owned lab cũ…';next.busy=true;render();
    try {
      const result=await cleanup(old.snapshot.lab_handle);
      if(owner===next)next.notice=result.cleared ? 'Đã xóa owned lab; các lab khác được giữ.' : 'Lab cũ không còn tồn tại.';
    }catch(e){if(owner===next)next.notice='Cleanup chưa xác nhận: '+e.message+'; không coi là đã xóa. Expiry 15 phút là dự phòng.';}
    finally{if(owner===next){next.busy=false;render();}}
  }
  function el(tag,text,cls) {
    const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(cls)node.className=cls;return node;
  }
  function details(title,data) {const d=el('details');d.append(el('summary',title),el('pre',typeof data==='string'?data:JSON.stringify(data,null,2)));return d;}
  function button(label,fn,disabled=false) {
    const b=el('button',label,'secondary');b.type='button';b.disabled=disabled;b.onclick=fn;return b;
  }
  function locked() {return owner.busy || owner.uncertain || !owner.snapshot;}
  function selected() {return owner.snapshot?.nodes.find(n=>n.node_id===$('fork-node').value);}
  function options(select,entries) {
    const value=select.value;select.replaceChildren(...entries.map(([v,label])=>{const o=el('option',label);o.value=v;return o;}));
    if(entries.some(([v])=>v===value))select.value=value;
  }
  function mineChoices(resetDraft=false) {
    const n=selected(),sameNode=!resetDraft && owner.draftNode===n?.node_id;
    const parent=$('fork-parent').value;
    const checked=sameNode ? new Set([...$('fork-txs').querySelectorAll('input:checked')].map(i=>i.value)) : new Set();
    options($('fork-parent'),(n?.blocks||[]).map(b=>[b.hash,'#'+b.height+' · '+b.classification+' · '+b.hash.slice(0,12)]));
    if(n)$('fork-parent').value=sameNode && n.blocks.some(b=>b.hash===parent) ? parent : n.tip_hash;
    owner.draftNode=n?.node_id;
    $('fork-txs').replaceChildren(...(n?.mempool||[]).map(tx=>{
      const label=el('label',undefined,'fork-tx');const input=el('input');input.type='checkbox';input.value=tx.tx_id;input.checked=checked.has(tx.tx_id);
      label.append(input,el('span',(tx.tx_type||'ISSUE')+' · '+(tx.payload?.label||tx.payload?.reason||'')+' · '+tx.tx_id,'digest'));return label;
    }));
  }
  function renderNode(n) {
    const card=el('article',undefined,'panel fork-node-card');card.append(el('h3',n.node_id));
    card.append(el('p',n.status+' · height '+n.height+' · work '+n.chain_work+' · '+(n.chain_valid?'Chuỗi hợp lệ':'Chuỗi không hợp lệ')));
    if(n.validity_reason)card.append(el('p',n.validity_reason));
    card.append(details('Tip đầy đủ',n.tip_hash));
    card.append(el('p','Cây block thực · active = nhánh chọn; stale = block đã biết ngoài nhánh chọn. Cuộn ngang để xem toàn bộ →','hint'));
    const scroll=el('div',undefined,'fork-tree');scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Cây block '+n.node_id+', cuộn ngang');
    // Parent arrows and height columns are derived from the stored block index, not a demo snapshot.
    const levels=el('div',undefined,'fork-levels');
    const heights=[...new Set(n.blocks.map(b=>b.height))].sort((a,b)=>a-b);
    heights.forEach(height=>{
      const col=el('div',undefined,'fork-level');col.append(el('h4','Height '+height));
      n.blocks.filter(b=>b.height===height).forEach(b=>{
        const block=el('div',undefined,'fork-block '+b.classification);
        block.append(el('strong',b.classification+' · '+b.hash.slice(0,10)),
          el('p','← '+b.parent_hash.slice(0,10)+' · d='+b.difficulty+' · work='+b.work),
          details('Hash / cha / TX đầy đủ',b));col.append(block);
      });levels.append(col);
    });scroll.append(levels);card.append(scroll);
    card.append(details('Nhánh đã validate và cumulative work',n.branches));
    const orphans=el('div',undefined,'fork-orphans');orphans.append(el('h4','Orphan · chờ cha, chưa tính work'));
    if(!n.orphans.length)orphans.append(el('p','Không có orphan.'));
    n.orphans.forEach(o=>orphans.append(details('Orphan '+o.hash.slice(0,12)+' · còn '+Math.ceil(o.expires_in_seconds)+'s',o)));
    card.append(orphans);
    card.append(details('Mempool ('+n.mempool.length+' TX) · chữ ký / payload / ID',n.mempool));
    const credentials=el('div');credentials.append(el('h4','Hồ sơ theo node · chỉ active chain quyết định xác nhận'));
    Object.entries(n.credential_states).forEach(([id,c])=>{
      const section=el('section');section.append(el('h5',id,'digest'));
      section.append(el('p',c.confirmed_status == null ? 'Chưa có trên active chain' : 'Đã xác nhận: '+c.confirmed_status));
      section.append(el('p','Pending chỉ là giao dịch đang chờ; stale là lịch sử ngoài nhánh chọn, không đổi trạng thái đã xác nhận.','hint'));
      const pending=el('div');pending.append(el('h6','Pending · chưa xác nhận'));
      (c.pending_transactions||[]).forEach(tx=>pending.append(el('p',tx.tx_type+' · '+tx.tx_id,'digest'),details('Payload / chữ ký đang chờ',tx)));
      if(!c.pending_transactions?.length)pending.append(el('p','Không có giao dịch đang chờ cho hồ sơ này.'));
      section.append(pending);
      [['confirmed_transactions','Active · đã xác nhận'],['stale_transactions','Stale · không quyết định trạng thái hiện tại']].forEach(([key,title])=>{
        const list=el('div');list.append(el('h6',title));
        (c[key]||[]).forEach(record=>list.append(el('p',record.transaction.tx_type+' · '+record.transaction.tx_id+' · block #'+record.height+' · '+record.block_hash,'digest'),details('Vị trí / nội dung giao dịch đầy đủ',record)));
        if(!c[key]?.length)list.append(el('p','Không có vị trí giao dịch thuộc nhóm này.'));
        section.append(list);
      });
      section.append(details('Issuer và projection đầy đủ từ backend',c));credentials.append(section);
    });
    if(!Object.keys(n.credential_states).length)credentials.append(el('p','Chưa có credential.'));
    card.append(credentials);
    if(n.last_transition){const report=el('div');renderTransition(report,n.last_transition);card.append(report);}
    return card;
  }
  function renderTransition(target,t) {
    target.append(el('p','Work '+t.old_work+' → '+t.new_work+' · '+t.selection_reason));
    target.append(el('p','Tách '+t.detached_hashes.length+' block · gắn '+t.attached_hashes.length+' block · Restored thực: '+t.counts.restored+' TX'));
    target.append(el('p','Restored là giao dịch được nhận lại vào pending sau kiểm tra; chưa phải xác nhận lại.','hint'));
    target.append(el('p','Counts thực: '+Object.entries(t.counts).map(([k,v])=>k+'='+v).join(' · ')));
    t.transactions.forEach(tx=>target.append(el('p',tx.tx_id+' · '+tx.disposition+' · '+tx.reason_code+' — '+tx.message,'digest')));
    target.append(details('Ancestor / detached / attached / lý do đầy đủ',t));
  }
  function render() {
    const o=owner,s=o.snapshot;
    $('fork-status').textContent=o.notice;
    $('fork-create').disabled=o.busy || !!s;
    $('fork-refresh').disabled=o.busy || !s;
    // Reset stays available while a request is pending.
    $('fork-reset').disabled=false;
    $('fork-controls').querySelectorAll('button').forEach(b=>b.disabled=locked());
    $('fork-meta').textContent=s ? 'Revision '+s.revision+' · manual queue · hết hạn sau khoảng '+Math.ceil(s.expires_in_seconds)+'s'+(o.uncertain?' · snapshot cũ; cần Refresh trước thao tác mới':'') : 'Chưa có owned handle.';
    $('fork-nodes').replaceChildren(...(s?.nodes||[]).map(renderNode));
    $('fork-links').replaceChildren(...(s?.links||[]).map(link=> {
      const b=button(link.a+' ↔ '+link.b+' · '+(link.connected?'Nối':'Ngắt'),
        ()=>action('links',{changes:[{a:link.a,b:link.b,connected:!link.connected}]}),locked());return b;
    }));
    $('fork-pending').replaceChildren(...(s?.pending_messages||[]).map(m=>{
      const row=el('div',undefined,'fork-message');
      row.append(el('p',m.from+' → '+m.to+' · '+m.kind+' · '+(m.blocked_reason?'Bị chặn: '+m.blocked_reason:'Có thể giao')),
        details('ID và reference đầy đủ',m),
        button('Giao tin '+m.sequence,()=>action('deliver',{message_id:m.id}),locked()),
        button('Bỏ tin '+m.sequence,()=>action('discard',{message_id:m.id}),locked()));
      row.dataset.messageId=m.id;row.dataset.reference=m.reference||'';row.dataset.kind=m.kind;
      return row;
    }));
    if(s && !s.pending_messages.length)$('fork-pending').append(el('p','Không có tin đang chờ.'));
    const c=o.continuation,continuation=$('fork-continuation');continuation.replaceChildren();
    if(c){
      continuation.append(el('h3','Hành động tiếp theo của người học'),el('p',c.learning_goal||goals[o.scenario]));
      (c.next_steps||[]).forEach(step=>continuation.append(el('p',step)));
      continuation.append(details('Chỉ dẫn trả về từ backend',c));
      if(c.reconnect)continuation.append(button('Nối lại các link theo kịch bản',()=>action('links',{changes:c.reconnect}),locked()));
      [['message_id','Giao tin quyết định'],['child_message_id','Giao con trước'],['parent_message_id','Giao cha sau']].forEach(([key,label])=>{
        if(c[key])continuation.append(button(label,()=>action('deliver',{message_id:c[key]}),locked() || !s?.pending_messages.some(m=>m.id===c[key])));
      });
      if(c.remine_tx_ids?.length){
        const n=s?.nodes.find(n=>n.node_id===c.node_id);
        const pending=new Set((n?.mempool||[]).map(tx=>tx.tx_id));
        const canMine=n && c.remine_tx_ids.every(id=>pending.has(id)) && !s.pending_messages.some(m=>m.id===c.message_id);
        continuation.append(button('Đào lại REVOKE đang chờ',()=>{
          const current=owner.snapshot?.nodes.find(n=>n.node_id===c.node_id);
          if(current)action('mine',{node_id:c.node_id,parent_hash:current.tip_hash,difficulty:1,tx_ids:c.remine_tx_ids});
        },locked() || !canMine));
        continuation.append(el('p','Chỉ đào lại khi TxID trả về còn trong mempool của node sau giao tin; dùng tip và revision hiện tại.','hint'));
      }
      if(c.detached_tx_id)continuation.append(el('p','TX A: '+c.detached_tx_id+' · credential A: '+c.credential_id,'digest'));
    }
    const report=$('fork-report');report.replaceChildren();
    if(o.report){
      const r=o.report;report.append(el('p',r.outcome.code+' — '+r.outcome.message));
      if(r.mining)report.append(details('Kết quả mining thực (không suy ra năng lượng)',r.mining));
      if(r.setup_completed_steps)report.append(details('Các bước setup thực đã hoàn tất',r.setup_completed_steps));
      if(r.outcome.code==='scenario_incomplete'){
        report.append(el('p','Setup chưa hoàn tất; chỉ hiển thị phần backend đã thực hiện. Không có hành động quyết định sẵn. Reset & tạo lab mới để nạp lại.'));
        if(r.setup_failure)report.append(details('Lỗi setup thực · mã lý do và giới hạn',r.setup_failure));
      }
      if(r.transaction)report.append(details('Giao dịch đã ký và được nhận vào pending · chưa xác nhận',r.transaction));
      if(r.transition)renderTransition(report,r.transition);
      else report.append(el('p','Thao tác này không trả transition reorg mới.'));
    }else report.append(el('p','Thực hiện thao tác để đọc kết quả và nguyên nhân.'));
    $('fork-event-note').textContent=s?.events_truncated ? 'Nhật ký đã cắt bớt; chỉ giữ tối đa 200 events, cursor '+s.event_cursor+'. Không phải lịch sử đầy đủ.' : 'Nhật ký backend · cursor '+(s?.event_cursor||0);
    $('fork-events').replaceChildren(...(s?.events||[]).map(e=>el('li','#'+e.sequence+' · '+e.node_id+' · '+e.code+' — '+e.message)));
    $('fork-raw').textContent=s?JSON.stringify(s,null,2):'';
    if(s){mineChoices();$('fork-online').textContent=selected()?.status==='ONLINE'?'Đặt OFFLINE':'Đặt ONLINE';}
  }
  function leave() {
    const old=owner;owner=fresh();render();
    if(old.snapshot)fetch(base+'/'+encodeURIComponent(old.snapshot.lab_handle),{method:'DELETE',credentials:'same-origin',keepalive:true}).catch(()=>{});
  }
  // Bind the independent lab.
  $('fork-controls').addEventListener('input',edit);
  $('fork-controls').addEventListener('change',edit);
  $('fork-create').onclick=()=>action('create');
  $('fork-refresh').onclick=refresh;
  $('fork-reset').onclick=reset;
  $('fork-node').onchange=()=>{mineChoices(true);$('fork-online').textContent=selected()?.status==='ONLINE'?'Đặt OFFLINE':'Đặt ONLINE';};
  $('fork-online').onclick=()=>action('nodes/'+$('fork-node').value+'/status',{status:selected()?.status==='ONLINE'?'OFFLINE':'ONLINE'});
  $('fork-sync').onclick=()=>action('sync',{node_id:$('fork-node').value});
  $('fork-issue-form').onsubmit=e=>{e.preventDefault();action('transactions',{node_id:$('fork-node').value,label:$('fork-label').value.trim()});};
  $('fork-credential-action').onchange=()=>{
    $('fork-credential-text-label').textContent=$('fork-credential-action').value==='ISSUE' ? 'Tiêu đề ISSUE (1–120 ký tự)' : 'Lý do REVOKE (1–120 ký tự)';
  };
  $('fork-credential-form').onsubmit=e=>{
    e.preventDefault();
    const type=$('fork-credential-action').value;
    action('credential-transactions',{node_id:$('fork-node').value,action:type,
      credential_id:$('fork-credential-id').value,
      [type==='ISSUE'?'label':'reason']:$('fork-credential-text').value});
  };
  ['C1','C2','C3'].forEach(scenario=>{
    $('fork-load-'+scenario).onclick=()=>action('scenario',{scenario});
  });
  $('fork-mine-form').onsubmit=e=>{
    e.preventDefault();action('mine',{node_id:$('fork-node').value,parent_hash:$('fork-parent').value,
      difficulty:Number($('fork-difficulty').value),tx_ids:[...$('fork-txs').querySelectorAll('input:checked')].map(i=>i.value)});
  };
  $('fork-load').onclick=()=>action('scenario',{scenario:$('fork-scenario').value});
  $('fork-scenario').onchange=()=>{$('fork-goal').textContent=goals[$('fork-scenario').value];};
  $('fork-goal').textContent=goals[$('fork-scenario').value];
  function tab(name) {
    ['practice','theory'].forEach(t=>{const b=$('fork-tab-'+t);b.setAttribute('aria-selected',String(t===name));b.tabIndex=t===name?0:-1;$('fork-'+t+'-panel').hidden=t!==name;});
  }
  ['practice','theory'].forEach((name,index)=>{
    $('fork-tab-'+name).onclick=()=>tab(name);
    $('fork-tab-'+name).onkeydown=e=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
      const next=e.key==='Home'?'practice':e.key==='End'?'theory':['practice','theory'][1-index];tab(next);$('fork-tab-'+next).focus();
    };
  });
  window.addEventListener('pagehide',leave);
  tab('practice');render();
})();
