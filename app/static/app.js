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
const available = row => row.error || row.release_error ? 'error' : row.checked_at === null ? 'unchecked' : row.sv_count>0 ? 'sv' : row.en_count>0 ? 'en' : 'none';
const matchCount = (m, lang) => (m.release_matches || {})[lang+'_candidates'] || 0;
const matchesFilter = (m,f) => f==='all' || (f==='svmatch' && matchCount(m,'sv')>0) || (f==='enmatch' && matchCount(m,'en')>0) || (f==='unmatched' && m.release_checked_at && matchCount(m,'sv')===0 && matchCount(m,'en')===0) || f===available(m);
const matchText = status => ({exact:'Samma namn',probable:'Trolig',possible:'Möjlig',none:'Ingen nammatch'})[status] || 'Okänd';
function matchBadge(status){return element('span',matchText(status),'pill match-label '+status)};
function pill(value, mode){
  if(value===null || value===undefined) return element('span','Ej kontrollerad','pill');
  return element('span',value>0 ? `${value} träffar` : 'Inga träffar', 'pill '+(value>0 ? mode : 'none'));
}
function render(){
  const query=$('query').value.toLocaleLowerCase('sv').trim(),filter=$('filter').value;
  const target=$('movies');target.replaceChildren();
  const filtered=rows.filter(m=>m.title.toLocaleLowerCase('sv').includes(query) && matchesFilter(m,filter));
  $('subheading').textContent=`Visar ${filtered.length} av ${rows.length} filmer utan videofil.`;
  if(!filtered.length){let tr=element('tr'); let td=element('td','Inga filmer matchar filtret.','empty');td.colSpan=6;tr.append(td);target.append(tr);return;}
  for(const m of filtered){
    const tr=element('tr');
    const first=element('td'); first.append(element('span',m.title,'film-name'),element('span',m.year||'','film-year'));
    if(!m.monitored)first.append(element('div','Ej övervakad i Radarr','subinfo'));
    if(m.match_method==='title')first.append(element('div','Sökt med titel – kontrollera att filmen stämmer','subinfo'));
    if(m.error)first.append(element('div',m.error,'subinfo'));
    tr.append(first);
    const tdsv=element('td');tdsv.append(m.error ? element('span','Fel','pill err'):pill(m.sv_count,'sv'));tr.append(tdsv);
    const tden=element('td');tden.append(m.error ? element('span','Fel','pill err'):pill(m.en_count,'en'));tr.append(tden);
    const rel=element('td');
    if(m.release_error) rel.append(element('span','Radarr-fel','pill err'));
    else if(!m.release_checked_at) rel.append(element('span','Ej kontrollerad','pill'));
    else if(matchCount(m,'sv'))rel.append(element('span',matchCount(m,'sv')+' SV-kandidater','pill sv'));
    else if(matchCount(m,'en'))rel.append(element('span',matchCount(m,'en')+' EN-kandidater','pill en'));
    else rel.append(element('span',(m.release_count || 0)+' releaser · ingen nammatch','pill none'));
    tr.append(rel);
    tr.append(element('td',time(m.checked_at),'muted'));
    const act=element('td');const btn=element('button','Detaljer','button outline tiny');btn.onclick=()=>details(m.id);act.append(btn);tr.append(act);target.append(tr);
  }
}
function secureSubtitleUrl(value){
  try{let u=new URL(value);if(u.protocol==='https:' && (u.hostname==='opensubtitles.com'||u.hostname.endsWith('.opensubtitles.com')))return u.href;}catch{} return null;
}
function details(id, scroll=true){
  const m=rows.find(x=>x.id===id);if(!m)return;selected=id;
  $('details').hidden=false;$('detail-title').textContent=`${m.title} (${m.year||'–'})`;
  $('detail-meta').textContent=`IMDb: ${m.imdb_id||'saknas'} · ${m.match_method==='title'?'Titelmatchning (osäker)':'IMDb-matchning'} · Uppdaterad: ${time(m.checked_at)}`;
  const body=$('detail-body');body.replaceChildren();const wrap=element('div',undefined,'results');
  for(const [lang,name] of [['sv','Svenska'],['en','Engelska']]){
    let box=element('div',undefined,'resultbox');box.append(element('h3',name));let list=(m.results||{})[lang]||[];
    if(!list.length)box.append(element('p',m.checked_at ? 'Inga träffar i sparade API-resultat.' : 'Inte kontrollerad.','hint'));
    for(const sub of list.slice(0,5)){
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
  const releasePanel=element('section',undefined,'releasebox');
  releasePanel.append(element('h3','Radarr-releaser jämförda med OpenSubtitles'));
  releasePanel.append(element('p','Namnbaserad uppskattning: samma namn / trolig / möjlig är inte verifierad textsynk. Avvisade Radarr-releaser markeras separat.','hint'));
  const matches=m.release_matches || {}, releases=matches.releases || [];
  if(m.release_error)releasePanel.append(element('p','Radarr-sökning misslyckades: '+m.release_error,'notice'));
  if(m.subtitles_incomplete || m.release_incomplete)releasePanel.append(element('p','Endast en del av resultaten kunde jämföras. Saknad match betyder inte att undertexter saknas.','notice'));
  if(!m.release_checked_at)releasePanel.append(element('p','Ingen Radarr-sökning genomförd. Kör Kontrollera undertexter.','hint'));
  else if(!releases.length)releasePanel.append(element('p',(m.release_count||0)+' releaser hittades; inga kandidater att visa.','hint'));
  else {
    releasePanel.append(element('p',(m.release_count||0)+' releaser från Radarr. '+matchCount(m,'sv')+' SV-matchningar och '+matchCount(m,'en')+' EN-matchningar (ej Radarr-avvisade).','hint'));
    const box=element('div',undefined,'release-list'),tbl=element('table',undefined,'release-table');
    const head=element('thead'),headrow=element('tr');
    for(const value of ['Radarr-release / indexer','Kvalitet','Svenska','Engelska'])headrow.append(element('th',value));
    head.append(headrow);tbl.append(head);const bodyRows=element('tbody');
    for(const release of releases){
      const tr=element('tr');
      if(release.rejected)tr.className='rejected';
      const title=element('td');
      title.append(element('div',release.title||'Utan titel','release-title'),
                   element('div',release.indexer||'Okänd indexer','hint'));
      if(release.rejected)title.append(element('div','Avvisad av Radarr: '+((release.rejections||[]).join('; ')||'Okänd anledning'),'hint'));
      tr.append(title,element('td',release.quality||'–'));
      for(const lang of ['sv','en']){
        const td=element('td'), match=(release.matches||{})[lang]||{status:'none'};
        td.append(matchBadge(match.status));
        if(match.subtitle){
          td.append(element('div',match.subtitle.release||'','hint'));
          const link=secureSubtitleUrl(match.subtitle.page_url);
          if(link){
            const a=element('a','Visa undertext ↗');a.href=link;a.target='_blank';a.rel='noopener noreferrer';
            td.append(a);
          }
        }
        tr.append(td);
      }
      bodyRows.append(tr);
    }
    tbl.append(bodyRows);box.append(tbl);releasePanel.append(box);
  }
  body.append(releasePanel);
  let bar=element('div');bar.style.padding='0 20px 16px';let b=element('button','Kontrollera den här filmen igen','button primary small');b.onclick=()=>action('/api/scan',{movie_id:m.id,force:true});bar.append(b);body.append(bar);
  if(scroll)$('details').scrollIntoView({behavior:'smooth',block:'start'});
}
async function action(path,body={}){
  try{await api(path,body);await refresh();}catch(e){alert(e.message)}
}
async function refresh(){
  try{
    const [status,list]=await Promise.all([api('/api/status'),api('/api/movies')]);
    rows=list.movies;
    const s=status.summary,j=status.job,c=status.settings;
    $('stat-missing').textContent=s.missing;$('stat-sv').textContent=s.swedish;$('stat-en').textContent=s.english_only;$('stat-none').textContent=s.none;$('stat-svmatch').textContent=s.sv_release_match ?? 0;
    const errors=[];if(!c.radarr_configured)errors.push('RADARR_API_KEY saknas i .env.');if(!c.opensubtitles_configured)errors.push('OPENSUBTITLES_API_KEY saknas i .env.');
    $('config').hidden=!errors.length;if(errors.length)$('config').textContent=errors.join(' ') + ' Uppdatera konfigurationen och starta om containern.';
    $('job').hidden=!j.running && !j.message;
    $('job-name').textContent=j.running ? (j.action==='scan'?'Söker undertexter …':'Synkar Radarr …') : (j.message||'');
    $('job-count').textContent=j.total ? `${j.done}/${j.total}` : '';
    $('job-message').textContent=j.current||j.message||'';
    $('progress').style.width=j.total ? `${100*j.done/j.total}%` : '0%';
    for(const key of ['sync','scan','force'])$(key).disabled=!!j.running;
    render();
    if(selected !== null && !$('details').hidden){const oldSelected=selected;const m=rows.find(r=>r.id===oldSelected);if(m) details(oldSelected,false);}
    $('updated').textContent=`Kontrollerade filmer: ${s.checked}/${s.missing}.`;
  }catch(e){$('config').hidden=false;$('config').textContent=`Kan inte läsa servern: ${e.message}`}
}
$('sync').onclick=()=>action('/api/sync');$('scan').onclick=()=>action('/api/scan',{});$('force').onclick=()=>{if(confirm('Kontrollera alla filmer igen, även sparade resultat?'))action('/api/scan',{force:true})};
$('query').oninput=render;$('filter').onchange=render;$('close').onclick=()=>{$('details').hidden=true;selected=null};
refresh();setInterval(refresh,2500);
