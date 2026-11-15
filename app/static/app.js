const $ = id => document.getElementById(id);
let rows = [], selected = null, lastRunning = false;
const api = async (path, data) => {
  const r = await fetch(path, data === undefined ? {} : {
    method: 'POST', headers: {'Content-Type':'application/json','X-Requested-With':'SubtitleChecker'},
    body: JSON.stringify(data),
  });
  const payload = await r.json();
  if(!r.ok) throw Error(payload.error || 'Fel vid anslutning');
  return payload;
};
const element = (tag, text, cls) => { const n=document.createElement(tag); if(text!==undefined)n.textContent=String(text); if(cls)n.className=cls; return n; };
const time = text => { if(!text) return 'Inte kontrollerad'; try{return new Date(text).toLocaleString('sv-SE')}catch{return text} };
const available = row => row.error ? 'error' : row.checked_at === null ? 'unchecked' : row.sv_count>0 ? 'sv' : row.en_count>0 ? 'en' : 'none';
function pill(value, mode){
  if(value===null || value===undefined) return element('span','Ej kontrollerad','pill');
  return element('span',value>0 ? `${value} träffar` : 'Inga träffar', 'pill '+(value>0 ? mode : 'none'));
}
function render(){
  const query=$('query').value.toLocaleLowerCase('sv').trim(),filter=$('filter').value;
  const target=$('movies');target.replaceChildren();
  const filtered=rows.filter(m=>m.title.toLocaleLowerCase('sv').includes(query) && (filter==='all'||filter===available(m)));
  $('subheading').textContent=`Visar ${filtered.length} av ${rows.length} filmer utan videofil.`;
  if(!filtered.length){let tr=element('tr'); let td=element('td','Inga filmer matchar filtret.','empty');td.colSpan=5;tr.append(td);target.append(tr);return;}
  for(const m of filtered){
    const tr=element('tr');
    const first=element('td'); first.append(element('span',m.title,'film-name'),element('span',m.year||'','film-year'));
    if(!m.monitored)first.append(element('div','Ej övervakad i Radarr','subinfo'));
    if(m.match_method==='title')first.append(element('div','Sökt med titel – kontrollera att filmen stämmer','subinfo'));
    if(m.error)first.append(element('div',m.error,'subinfo'));
    tr.append(first);
    const tdsv=element('td');tdsv.append(m.error ? element('span','Fel','pill err'):pill(m.sv_count,'sv'));tr.append(tdsv);
    const tden=element('td');tden.append(m.error ? element('span','Fel','pill err'):pill(m.en_count,'en'));tr.append(tden);
    tr.append(element('td',time(m.checked_at),'muted'));
    const act=element('td');const btn=element('button','Detaljer','button outline tiny');btn.onclick=()=>details(m.id);act.append(btn);tr.append(act);target.append(tr);
  }
}
function secureSubtitleUrl(value){
  try{let u=new URL(value);if(u.protocol==='https:' && (u.hostname==='opensubtitles.com'||u.hostname.endsWith('.opensubtitles.com')))return u.href;}catch{} return null;
}
function details(id){
  const m=rows.find(x=>x.id===id);if(!m)return;selected=id;
  $('details').hidden=false;$('detail-title').textContent=`${m.title} (${m.year||'–'})`;
  $('detail-meta').textContent=`IMDb: ${m.imdb_id||'saknas'} · ${m.match_method==='title'?'Titelmatchning (osäker)':'IMDb-matchning'} · Uppdaterad: ${time(m.checked_at)}`;
  const body=$('detail-body');body.replaceChildren();const wrap=element('div',undefined,'results');
  for(const [lang,name] of [['sv','Svenska'],['en','Engelska']]){
    let box=element('div',undefined,'resultbox');box.append(element('h3',name));let list=(m.results||{})[lang]||[];
    if(!list.length)box.append(element('p',m.checked_at ? 'Inga träffar i sparade API-resultat.' : 'Inte kontrollerad.','hint'));
    for(const sub of list){
      let r=element('div',undefined,'subtitle');r.append(element('div',sub.release||'Okänt release-namn'));
      const flags=[`${sub.downloads||0} nedladdningar`];if(sub.hearing_impaired)flags.push('HI');if(sub.machine_translated)flags.push('maskinöversatt');
      r.append(element('div',flags.join(' · '),'hint'));
      const u=secureSubtitleUrl(sub.page_url);
      if(u){let a=element('a','Visa hos OpenSubtitles ↗');a.href=u;a.target='_blank';a.rel='noopener noreferrer';r.append(a)}
      box.append(r);
    }
    wrap.append(box);
  }
  body.append(wrap);
  let bar=element('div');bar.style.padding='0 20px 16px';let b=element('button','Kontrollera den här filmen igen','button primary small');b.onclick=()=>action('/api/scan',{movie_id:m.id,force:true});bar.append(b);body.append(bar);
  $('details').scrollIntoView({behavior:'smooth',block:'start'});
}
async function action(path,body={}){
  try{await api(path,body);await refresh();}catch(e){alert(e.message)}
}
async function refresh(){
  try{
    const [status,list]=await Promise.all([api('/api/status'),api('/api/movies')]);
    rows=list.movies;
    const s=status.summary,j=status.job,c=status.settings;
    $('stat-missing').textContent=s.missing;$('stat-sv').textContent=s.swedish;$('stat-en').textContent=s.english_only;$('stat-none').textContent=s.none;
    const errors=[];if(!c.radarr_configured)errors.push('RADARR_API_KEY saknas i .env.');if(!c.opensubtitles_configured)errors.push('OPENSUBTITLES_API_KEY saknas i .env.');
    $('config').hidden=!errors.length;if(errors.length)$('config').textContent=errors.join(' ') + ' Uppdatera konfigurationen och starta om containern.';
    $('job').hidden=!j.running && !j.message;
    $('job-name').textContent=j.running ? (j.action==='scan'?'Söker undertexter …':'Synkar Radarr …') : (j.message||'');
    $('job-count').textContent=j.total ? `${j.done}/${j.total}` : '';
    $('job-message').textContent=j.current||j.message||'';
    $('progress').style.width=j.total ? `${100*j.done/j.total}%` : '0%';
    for(const key of ['sync','scan','force'])$(key).disabled=!!j.running;
    render();
    if(selected !== null && !$('details').hidden){const oldSelected=selected;const m=rows.find(r=>r.id===oldSelected);if(m) $('detail-meta').textContent=`IMDb: ${m.imdb_id||'saknas'} · ${m.match_method==='title'?'Titelmatchning (osäker)':'IMDb-matchning'} · Uppdaterad: ${time(m.checked_at)}`;}
    $('updated').textContent=`Kontrollerade filmer: ${s.checked}/${s.missing}.`;
  }catch(e){$('config').hidden=false;$('config').textContent=`Kan inte läsa servern: ${e.message}`}
}
$('sync').onclick=()=>action('/api/sync');$('scan').onclick=()=>action('/api/scan',{});$('force').onclick=()=>{if(confirm('Kontrollera alla filmer igen, även sparade resultat?'))action('/api/scan',{force:true})};
$('query').oninput=render;$('filter').onchange=render;$('close').onclick=()=>{$('details').hidden=true;selected=null};
refresh();setInterval(refresh,2500);
