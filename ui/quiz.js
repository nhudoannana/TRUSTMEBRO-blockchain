/* Standalone self-study owner; simulation sessions and keys never enter this page. */
(()=>{
'use strict';
const PROGRESS_KEY='trustmebro-quiz-progress-v1',ATTEMPT_KEY='trustmebro-quiz-attempt-v1';
const BANK_VERSION='core-2026-10-11-v1',QUOTAS={sha:4,ecdsa:2,blocks:2,merkle:4,fork:3,oaep:2,pss:3};
const SOURCE_IDS=[23,25,61,62,67,98,100,101,102,104,109,110,125,158,159,160];
const APPROVED_IDS=new Set([...SOURCE_IDS.map(n=>'src-'+String(n).padStart(3,'0')),
 ...[['ecdsa',2],['merkle',4],['fork',4],['oaep',4],['pss',6]].flatMap(([t,n])=>Array.from({length:n},(_,i)=>'lab-'+t+'-'+String(i+1).padStart(2,'0')))]);
const LAB_URLS=new Set(['sha','signatures','blocks','merkle','fork','rsa-oaep','rsa-pss'].map(t=>'/ui/labs.html#'+t));
let bank=null,byId=new Map(),progress=null,attempt=null,revision=0,loading=false,timer=null,home=true;
const $=id=>document.getElementById(id);
const plain=v=>v!==null&&typeof v==='object'&&!Array.isArray(v)&&Object.getPrototypeOf(v)===Object.prototype;
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const integer=v=>Number.isSafeInteger(v)&&v>=0;
const text=v=>typeof v==='string'&&v.trim().length>0;
function requireValid(ok){if(!ok)throw new Error('Dữ liệu Quiz không hợp lệ.');}
function validateBank(value){
 requireValid(plain(value)&&value.schemaVersion===1&&value.bankVersion===BANK_VERSION&&value.reviewedAgainst==='1226846e7a60a18d40f48cff764c8173cb4fc367');
 requireValid(Array.isArray(value.topics)&&value.topics.length===7&&Array.isArray(value.questions)&&value.questions.length===36);
 const topics=new Set();
 for(const t of value.topics){requireValid(plain(t)&&own(QUOTAS,t.id)&&!topics.has(t.id)&&text(t.title)&&t.scope==='implemented-labs');topics.add(t.id);}
 const ids=new Set();
 for(const q of value.questions){
  requireValid(plain(q)&&APPROVED_IDS.has(q.id)&&!ids.has(q.id)&&topics.has(q.topicId)&&q.scope==='implemented-labs'&&q.reviewStatus==='reviewed');
  ids.add(q.id);requireValid(text(q.prompt)&&text(q.explanation)&&['Dễ','Vừa','Khó'].includes(q.level));
  requireValid(Array.isArray(q.options)&&q.options.length===4&&q.options.every((o,i)=>plain(o)&&o.id==='abcd'[i]&&text(o.text))&&new Set(q.options.map(o=>o.text)).size===4&&'abcd'.includes(q.correctOptionId)&&q.correctOptionId.length===1);
  requireValid(Array.isArray(q.labLinks)&&q.labLinks.length>0&&q.labLinks.every(l=>plain(l)&&text(l.label)&&LAB_URLS.has(l.href)));
  requireValid(Array.isArray(q.evidence)&&q.evidence.length>0&&q.evidence.every(e=>plain(e)&&text(e.file)&&text(e.functionOrSection)));
 }
 for(const [topic,n] of Object.entries(QUOTAS))requireValid(value.questions.filter(q=>q.topicId===topic).length>=n);
 return value;
}
function shuffle(rows){
 const result=[...rows];
 for(let i=result.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[result[i],result[j]]=[result[j],result[i]];}
 return result;
}
function selectQuestions(mode,topic,level){
 requireValid(bank&&['practice','exam'].includes(mode));
 if(mode==='exam')return shuffle(Object.entries(QUOTAS).flatMap(([t,n])=>{
  const rows=shuffle(bank.questions.filter(q=>q.topicId===t));requireValid(rows.length>=n);return rows.slice(0,n).map(q=>q.id);
 }));
 const rows=bank.questions.filter(q=>q.topicId===topic&&(!level||q.level===level));
 requireValid(rows.length>0);return shuffle(rows.map(q=>q.id));
}
function scoreAttempt(a){
 const total=a.questionIds.length;let correct=0,incorrect=0,unanswered=0;
 for(const id of a.questionIds){
  if(!own(a.answers,id))unanswered++;
  else if(a.answers[id]===byId.get(id).correctOptionId)correct++;else incorrect++;
 }
 return {total,correct,incorrect,unanswered,percent:total?Math.round(correct/total*100):0,passed:total>0&&correct/total>=.7};
}
function freshProgress(){return {schemaVersion:1,bankVersion:bank.bankVersion,outcomes:{}};}
function validateProgress(v){
 requireValid(plain(v)&&v.schemaVersion===1&&v.bankVersion===bank.bankVersion&&plain(v.outcomes)&&Object.keys(v.outcomes).length<=36);
 for(const [id,o] of Object.entries(v.outcomes)){
  const q=byId.get(id);requireValid(q&&plain(o)&&q.options.some(p=>p.id===o.selectedOptionId)&&typeof o.correct==='boolean'&&o.correct===(o.selectedOptionId===q.correctOptionId)&&integer(o.answeredAtMs));
 }
 return v;
}
function validateAttempt(v){
 requireValid(plain(v)&&v.schemaVersion===1&&v.bankVersion===bank.bankVersion&&text(v.attemptId)&&v.attemptId.length<=100);
 requireValid(['practice','exam'].includes(v.mode)&&['active','finished'].includes(v.status)&&integer(v.startedAtMs)&&typeof v.progressRecorded==='boolean');
 requireValid(Array.isArray(v.questionIds)&&v.questionIds.length>0&&v.questionIds.length<=36&&new Set(v.questionIds).size===v.questionIds.length&&v.questionIds.every(id=>byId.has(id)));
 requireValid(integer(v.index)&&v.index<v.questionIds.length&&plain(v.answers));
 for(const [id,option] of Object.entries(v.answers))requireValid(v.questionIds.includes(id)&&byId.get(id).options.some(p=>p.id===option));
 requireValid(Array.isArray(v.confirmedIds)&&new Set(v.confirmedIds).size===v.confirmedIds.length&&v.confirmedIds.every(id=>v.questionIds.includes(id)&&own(v.answers,id)));
 if(v.mode==='practice'){
  requireValid(own(QUOTAS,v.topicId)&&(v.level===null||['Dễ','Vừa','Khó'].includes(v.level))&&v.deadlineMs===null&&v.durationMs===null);
  requireValid(v.questionIds.every(id=>byId.get(id).topicId===v.topicId&&(!v.level||byId.get(id).level===v.level)));
 }else{
  requireValid(v.topicId===null&&v.level===null&&v.confirmedIds.length===0&&v.questionIds.length===20);
  for(const [t,n] of Object.entries(QUOTAS))requireValid(v.questionIds.filter(id=>byId.get(id).topicId===t).length===n);
  requireValid((v.durationMs===null&&v.deadlineMs===null)||(v.durationMs===1200000&&integer(v.deadlineMs)&&v.deadlineMs===v.startedAtMs+v.durationMs));
 }
 requireValid(v.status==='active'?(v.finishedAtMs===null&&v.finishReason===null&&v.progressRecorded===false):
  (integer(v.finishedAtMs)&&v.finishedAtMs>=v.startedAtMs&&['submitted','timeout'].includes(v.finishReason)&&
   (v.finishReason!=='timeout'||v.deadlineMs!==null&&v.finishedAtMs>=v.deadlineMs)));
 return v;
}
function notice(message){$('quiz-notice').textContent=message;}
function readRecord(storage,key,validator){
 try{
  storage=globalThis[storage];
  const raw=storage.getItem(key);if(raw===null)return null;
  try{requireValid(new Blob([raw]).size<=32768);return validator(JSON.parse(raw));}
  catch{try{storage.removeItem(key);}catch{}notice('Dữ liệu Quiz không hợp lệ hoặc khác phiên bản, đã bỏ qua.');return null;}
 }catch{notice('Không thể đọc/lưu trên trình duyệt này; Quiz vẫn dùng được trong bộ nhớ, tải lại có thể mất bài.');return null;}
}
function writeRecord(storage,key,value){
 try{globalThis[storage].setItem(key,JSON.stringify(value));}
 catch{notice('Không thể lưu Quiz; bạn vẫn học được trong bộ nhớ, tải lại có thể mất bài.');}
}
function saveAttempt(){if(attempt)writeRecord('sessionStorage',ATTEMPT_KEY,attempt);}
function recordProgress(ids){
 const current=readRecord('localStorage',PROGRESS_KEY,validateProgress);
 if(current)progress={...current,outcomes:{...progress.outcomes,...current.outcomes}};
 for(const id of ids)if(own(attempt.answers,id))progress.outcomes[id]={selectedOptionId:attempt.answers[id],correct:attempt.answers[id]===byId.get(id).correctOptionId,answeredAtMs:Date.now()};
 writeRecord('localStorage',PROGRESS_KEY,progress);refreshSummary();
}
function stopTimer(){if(timer!==null)clearInterval(timer);timer=null;}
function startTimer(){
 stopTimer();if(!attempt||attempt.status!=='active'||attempt.deadlineMs===null)return;
 const owner=revision;timer=setInterval(()=>{if(owner===revision)tick();},1000);tick();
}
function startAttempt(mode,topic,level,timed){
 if(loading||!bank)return;
 const selected=selectQuestions(mode,topic,level);
 stopTimer();revision++;home=false;
 const now=Date.now(),duration=mode==='exam'&&timed?1200000:null;
 attempt={schemaVersion:1,bankVersion:bank.bankVersion,attemptId:crypto.randomUUID(),mode,topicId:mode==='practice'?topic:null,level:mode==='practice'?level:null,
 questionIds:selected,index:0,answers:{},confirmedIds:[],status:'active',startedAtMs:now,deadlineMs:duration===null?null:now+duration,durationMs:duration,finishedAtMs:null,finishReason:null,progressRecorded:false};
 saveAttempt();render(true);startTimer();
}
function expire(){
 if(attempt&&attempt.status==='active'&&attempt.deadlineMs!==null&&Date.now()>=attempt.deadlineMs){finishAttempt('timeout');return true;}
 return false;
}
function selectOption(option){
 if(expire()||!attempt||attempt.status!=='active')return;
 const id=attempt.questionIds[attempt.index];
 if(attempt.confirmedIds.includes(id))return;
 if(option===null)delete attempt.answers[id];else{
  if(!byId.get(id).options.some(o=>o.id===option))return;attempt.answers[id]=option;
 }
 saveAttempt();updateNavigation();$('check-answer').disabled=!own(attempt.answers,id);
}
function checkPracticeAnswer(){
 if(!attempt||attempt.mode!=='practice'||attempt.status!=='active')return;
 const id=attempt.questionIds[attempt.index];if(!own(attempt.answers,id)||attempt.confirmedIds.includes(id))return;
 attempt.confirmedIds.push(id);recordProgress([id]);saveAttempt();render(false);$('question-feedback').focus();
}
function finishAttempt(reason){
 if(!attempt||attempt.status!=='active')return;
 if(reason!=='timeout'&&attempt.deadlineMs!==null&&Date.now()>=attempt.deadlineMs)reason='timeout';
 attempt.status='finished';attempt.finishedAtMs=Date.now();attempt.finishReason=reason;
 stopTimer();recordProgress(attempt.questionIds);attempt.progressRecorded=true;saveAttempt();home=false;render(true);
}
function restoreAttempt(){
 stopTimer();attempt=readRecord('sessionStorage',ATTEMPT_KEY,validateAttempt);
 home=attempt===null;if(attempt&&!expire()){render(false);startTimer();}
}
function resetQuiz(){
 revision++;stopTimer();loading=false;attempt=null;home=true;
 $('retry-bank').disabled=false;$('start-practice').disabled=!bank;$('start-exam').disabled=!bank;
 try{localStorage.removeItem(PROGRESS_KEY);sessionStorage.removeItem(ATTEMPT_KEY);}
 catch{notice('Không thể xóa dữ liệu lưu; bài trong bộ nhớ đã được đặt lại.');}
 if(bank)progress=freshProgress();$('prediction-text').value='';
 render(true);refreshSummary();
}
function leaveAttempt(){home=true;saveAttempt();render(true);}
function resumeAttempt(){if(!attempt)return;home=false;if(!expire()){render(true);startTimer();}}
function tick(){
 if(expire()||!attempt||attempt.status!=='active')return;
 const ms=attempt.deadlineMs===null?null:Math.max(0,attempt.deadlineMs-Date.now());
 $('timer').textContent=ms===null?'Không tính giờ':Math.floor(Math.ceil(ms/1000)/60)+' phút · '+Math.ceil(ms/1000)%60+' giây còn lại';
 if(ms!==null&&[120,60].includes(Math.ceil(ms/1000)))$('time-notice').textContent='Còn '+Math.ceil(ms/1000)+' giây.';
}
async function loadBank(){
 const owner=++revision;startTimer();loading=true;$('retry-bank').disabled=true;$('start-practice').disabled=true;$('start-exam').disabled=true;
 notice('Đang tải tập câu hỏi đã review…');
 try{
  const response=await fetch('/ui/quiz_questions.json',{cache:'no-cache'});if(owner!==revision)return;
  if(!response.ok)throw Error('Không tải được câu hỏi. Hãy thử lại.');
  const value=validateBank(await response.json());if(owner!==revision)return;
  bank=value;byId=new Map(bank.questions.map(q=>[q.id,q]));notice('');
  progress=readRecord('localStorage',PROGRESS_KEY,validateProgress)||freshProgress();
  fillTopics();restoreAttempt();refreshSummary();
 }catch(error){if(owner===revision)notice(error.message+' Hãy tải lại câu hỏi.');}
 finally{if(owner===revision){loading=false;$('retry-bank').disabled=false;$('start-practice').disabled=!bank;$('start-exam').disabled=!bank;updateFilter();render(false);}}
}
function node(tag,content,cls){
 const e=document.createElement(tag);if(content!==undefined)e.textContent=content;if(cls)e.className=cls;return e;
}
function updateFilter(){
 const count=bank?bank.questions.filter(q=>q.topicId===$('topic').value&&(!$('level').value||q.level===$('level').value)).length:0;
 $('start-practice').disabled=loading||count===0;
 $('filter-notice').textContent=bank&&count===0?'Không có câu đã review phù hợp; hãy chọn mức khác.':'';
}
function fillTopics(){
 $('topic').replaceChildren(...bank.topics.map(t=>{const o=node('option',t.title+' ('+bank.questions.filter(q=>q.topicId===t.id).length+')');o.value=t.id;return o;}));
}
function refreshSummary(){
 if(!bank||!progress)return;
 const values=Object.values(progress.outcomes);
 $('progress-summary').textContent=values.length+'/'+bank.questions.length+' câu đã trả lời và chấm · '+values.filter(v=>v.correct).length+' đáp án gần nhất đúng. Đây là tập ban đầu đã review, không bao phủ toàn bộ lab.';
}
function labLinks(q,container){
 for(const link of q.labLinks){const a=node('a','Thử lại: '+link.label+' (tab mới)');a.href=link.href;a.target='_blank';a.rel='noopener';container.append(a);}
}
function explanation(q,selected,container){
 const label=selected===undefined?'Chưa trả lời':selected===q.correctOptionId?'Đúng':'Sai';
 container.append(node('p',label,'outcome'),node('p','Bạn chọn: '+(selected===undefined?'Chưa trả lời':q.options.find(o=>o.id===selected).text)),
 node('p','Đáp án đúng: '+q.options.find(o=>o.id===q.correctOptionId).text),node('p',q.explanation));
 labLinks(q,container);
}
function updateNavigation(){
 if(!attempt)return;
 const id=attempt.questionIds[attempt.index];
 $('question-position').textContent='Câu '+(attempt.index+1)+'/'+attempt.questionIds.length+' · '+(attempt.mode==='exam'?'Bài hỗn hợp':'Luyện chủ đề');
 for(const [i,button] of [...$('question-nav').children].entries()){
  const qid=attempt.questionIds[i],state=attempt.confirmedIds.includes(qid)?'đã kiểm tra':own(attempt.answers,qid)?'đã chọn':'chưa trả lời';
  button.setAttribute('aria-label','Câu '+(i+1)+' — '+state);button.setAttribute('aria-current',i===attempt.index?'step':'false');
 }
 $('prev-question').disabled=attempt.index===0;$('next-question').disabled=attempt.index===attempt.questionIds.length-1;
 $('skip-question').disabled=attempt.index===attempt.questionIds.length-1;
}
function jump(index){
 if(expire()||!attempt||attempt.status!=='active')return;
 attempt.index=index;saveAttempt();render(true);
}
function render(focus){
 $('setup').hidden=!home;
 $('continue-attempt').hidden=!attempt;
 $('attempt-view').hidden=home||!attempt||attempt.status!=='active';
 $('result-view').hidden=home||!attempt||attempt.status!=='finished';
 $('question-feedback').replaceChildren();
 if(!attempt||home){if(focus)$('practice-title').focus();return;}
 if(attempt.status==='finished'){
  const score=scoreAttempt(attempt);
  $('score').textContent=score.correct+'/'+score.total+' đúng · '+score.incorrect+' sai · '+score.unanswered+' chưa trả lời · '+score.percent+'% · '+(score.passed?'Đạt':'Chưa đạt')+' ngưỡng tự đánh giá 70%.';
  $('finish-reason').textContent=attempt.finishReason==='timeout'?'Hết thời gian; các câu chưa chọn được tính chưa trả lời.':'Đã kết thúc bài.';
  $('review-list').replaceChildren(...attempt.questionIds.map((id,i)=>{const q=byId.get(id),item=node('li');item.append(node('h3','Câu '+(i+1)+': '+q.prompt));explanation(q,attempt.answers[id],item);return item;}));
  if(focus)$('results-title').focus();return;
 }
 const id=attempt.questionIds[attempt.index],q=byId.get(id),locked=attempt.confirmedIds.includes(id);
 $('question').textContent=q.prompt;$('options').replaceChildren(...q.options.map(o=>{
  const label=node('label',undefined,'option'),input=node('input');input.type='radio';input.name='quiz-answer';input.value=o.id;input.checked=attempt.answers[id]===o.id;input.disabled=locked;
  input.addEventListener('change',()=>selectOption(o.id));label.append(input,node('span',o.text));return label;
 }));
 $('question-nav').replaceChildren(...attempt.questionIds.map((_,i)=>{const b=node('button',String(i+1));b.type='button';b.onclick=()=>jump(i);return b;}));
 $('check-answer').hidden=attempt.mode!=='practice';$('check-answer').disabled=locked||!own(attempt.answers,id);
 $('clear-answer').disabled=locked;$('question-feedback').hidden=!locked;
 if(locked)explanation(q,attempt.answers[id],$('question-feedback'));
 updateNavigation();tick();if(focus)$('question').focus();
}
// Browser wiring
function applyTheme(theme){
 document.documentElement.dataset.theme=theme;
 $('theme-toggle').setAttribute('aria-pressed',String(theme==='light'));
 $('theme-toggle').title=theme==='light'?'Chế độ tối':'Chế độ sáng';
 try{localStorage.setItem('trustmebro-theme',theme);}catch{}
}
function restoreTheme(){
 try{applyTheme(localStorage.getItem('trustmebro-theme')==='light'?'light':'dark');}
 catch{applyTheme(document.documentElement.dataset.theme||'dark');}
}
$('theme-toggle').onclick=()=>applyTheme(document.documentElement.dataset.theme==='light'?'dark':'light');
$('retry-bank').onclick=loadBank;
$('topic').onchange=updateFilter;$('level').onchange=updateFilter;
$('start-practice').onclick=()=>{try{startAttempt('practice',$('topic').value,$('level').value||null,false);}catch{notice('Không có câu đã review phù hợp bộ lọc; hãy chọn mức khác.');}};
$('start-exam').onclick=()=>startAttempt('exam',null,null,$('timed').checked);
$('check-answer').onclick=checkPracticeAnswer;
$('clear-answer').onclick=()=>{selectOption(null);render(false);};
$('prev-question').onclick=()=>jump(attempt.index-1);
$('next-question').onclick=()=>jump(attempt.index+1);
$('skip-question').onclick=()=>jump(attempt.index+1);
$('submit-attempt').onclick=()=>{
 if(expire()||!attempt||attempt.status!=='active')return;
 const answered=Object.keys(attempt.answers).length;
 if(confirm('Kết thúc bài: '+answered+' đã chọn, '+(attempt.questionIds.length-answered)+' chưa trả lời?'))finishAttempt('submitted');
};
$('leave-attempt').onclick=()=>{if(confirm('Lưu bài và về lựa chọn? Thời gian vẫn chạy nếu có tính giờ.'))leaveAttempt();};
$('continue-attempt').onclick=resumeAttempt;
$('new-attempt').onclick=()=>{home=true;render(true);};
$('reset-quiz').onclick=()=>{if(confirm('Xóa tiến độ Quiz và bài trong tab này? Không xóa trạng thái lab hay theme.'))resetQuiz();};
window.addEventListener('storage',event=>{
 if(event.key==='trustmebro-theme')restoreTheme();
 if(bank&&event.key===PROGRESS_KEY){progress=readRecord('localStorage',PROGRESS_KEY,validateProgress)||freshProgress();refreshSummary();}
});
window.addEventListener('pageshow',()=>{restoreTheme();if(bank){if(!expire())startTimer();}});
restoreTheme();loadBank();
})();
