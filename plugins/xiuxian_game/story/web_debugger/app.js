(() => {
'use strict';
const R = window.StoryWebRuntime;
const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
const text = value => typeof value === 'string' ? value : JSON.stringify(value);
const el = (tag, className, content) => { const n = document.createElement(tag); if (className) n.className = className; if (content !== undefined) n.textContent = content; return n; };
const labels = {nickname:'玩家名',level:'境界等级',hp:'血量',max_hp:'血量上限',mp:'理智',max_mp:'理智上限',gold:'灵石',exp:'修为',attack:'攻击',defense:'防御',agility:'身法',luck:'气运',constitution:'体质',completed_trials:'已通关试炼'};
let hasDocument = false, story = null, session = null, initialPlayer = clone(R.defaults), issues = [], raw = '', filename = '', undo = [], editorMode = 'story';
const demo = {id:'雾中来信',title:'雾中来信',description:'一个用来熟悉试炼工坊的简短故事。',start_node:'arrival',nodes:{arrival:{type:'story',content:'暮色沉入山谷，你在一座废弃驿站前停下脚步。\n\n门缝里，夹着一封写给 {player_name} 的信。信封上只有四个字：\n\n「莫信灯火。」',effects:{variables:{has_letter:true,courage:0}},next:'door'},door:{type:'choice',content:'驿站深处亮着一盏灯。门外石阶上，一枚铜钱正映着月光。\n\n你打算怎么做？',options:[{id:1,text:'拾起铜钱，推门而入',effects:{player:{gold:'+5'},variables:{courage:'+1'}},next:'inside'},{id:2,text:'读完信，再踏入灯影',conditions:{story_has_letter:{'==':true}},effects:{variables:{read_letter:true}},next:'inside'},{id:3,text:'以十枚灵石，向守门人问路',conditions:{player_gold:{'>=':10}},effects:{player:{gold:'-10'},variables:{read_letter:true,courage:'+1'}},next:'inside'}]},inside:{type:'story',content:'灯芯忽然爆响，门后传来低语。\n\n你握紧手中的信，迈出了下一步。',next:[{if:{story_read_letter:{'==':true}},goto:'reward'},{goto:'ordinary'}]},reward:{type:'story',content:'信上的字在月光中重新排列。你终于看懂了回家的路。\n\n雾散之前，守门人将二十枚灵石放在你掌心。',effects:{player:{gold:'+20'},variables:{perfect_ending:true}},next:'perfect'},perfect:{type:'end',content:'你走出了山谷。\n\n身后的驿站化作薄雾，唯有掌中的温度还在。\n\n【完美结局 · 月下归途】',effects:{trial_success:true}},ordinary:{type:'end',content:'天亮时，你回到了原地。信封已经空了。\n\n有些答案，或许藏在未曾读完的字里。\n\n【普通结局 · 迷途知返】',effects:{trial_success:true}}}};
function notify(message) { $('notice').textContent = message; $('notice').hidden = !message; }
function tab(name) { document.querySelectorAll('[data-tab]').forEach(b => { const active = b.dataset.tab === name; b.classList.toggle('active',active); b.setAttribute('aria-selected',String(active)); }); ['state','checks','source'].forEach(k => $(`tab-${k}`).hidden = k !== name); }
function parseJSON(value) { return JSON.parse(value.replace(/^\uFEFF/,''), (key, val) => { if (['__proto__','prototype','constructor'].includes(key)) throw new Error(`不支持的字段名：${key}`); return val; }); }
function load(value, name='未命名剧本.json') {
  let parsed;
  try { parsed = parseJSON(value); } catch (error) { notify(`JSON 无法解析：${error.message}。可以通过“粘贴 / 编辑 JSON”修正。`); raw = value; return false; }
  hasDocument = true; raw = value; filename = name; story = parsed; session = null; undo = [];
  try { issues = R.validate(parsed); } catch(error) { issues = [{severity:'error',path:'$',message:`无法完成检查：${error.message}`}]; }
  if (!issues.some(i => i.severity === 'error')) { try { session = R.createSession(story,initialPlayer); } catch (error) { issues.push({severity:'error',path:'start_node',message:error.message}); } }
  notify(session ? `已加载 ${name}。${issues.length ? `发现 ${issues.length} 条提示，可在“检查”中查看。` : '检查通过，可以开始游玩。'}` : '剧本未通过检查，请修正错误后再试。');
  render(); if (!session) tab('checks'); return Boolean(session);
}
async function loadFile(file) { if (!file) return; try { load(await file.text(),file.name); } catch(error) { notify(`读取失败：${error.message}`); } }
function render() {
  const loaded = hasDocument;
  $('welcome').hidden = loaded; $('play').hidden = !session; $('invalid').hidden = !loaded || Boolean(session);
  $('title').textContent = loaded ? (typeof story?.title === 'string' ? story.title : filename) : '让故事，走一遍。';
  for (const id of ['restart','export','edit-player','edit-vars','edit-source']) $(id).disabled = !session;
  $('undo').disabled = !undo.length;
  renderChecks(); renderNodes(); renderState();
  if (!session) { $('source').textContent = '尚未进入剧本'; return; }
  const node = story.nodes[session.nodeId];
  $('type').textContent = ({story:'叙事',choice:'抉择',end:'结局'})[node.type];
  $('current-id').textContent = session.nodeId;
  const visited = new Set([session.nodeId,...session.history.flatMap(h => [h.from,h.to])]);
  $('progress').textContent = `已探索 ${visited.size} / ${Object.keys(story.nodes).length}`;
  $('content').textContent = R.formatContent(node.content || '',session.player,session.variables) || '（此节点没有正文）';
  $('source').textContent = JSON.stringify(node,null,2);
  $('ending').hidden = node.type !== 'end';
  const choices = $('choices'); choices.replaceChildren();
  if (node.type === 'story') { const b = el('button','choice','继续前行 →'); b.onclick = () => advance(); choices.append(b); }
  if (node.type === 'choice') {
    let visible = 0;
    for (const option of node.options) {
      const allowed = !Object.hasOwn(option,'conditions') || R.evaluateCondition(option.conditions,session.player,session.variables);
      if (allowed) visible++;
      if (!allowed && !$('show-hidden').checked) continue;
      const b = el('button',`choice${allowed ? '' : ' locked'}`); b.disabled = !allowed;
      b.append(el('span','choice-index',option.id));
      const body = el('span','choice-body',R.formatContent(option.text,session.player,session.variables));
      if ($('show-hidden').checked && option.conditions) body.append(el('span','condition-hint',`${allowed ? '条件满足' : '条件未满足'} · ${JSON.stringify(option.conditions)}`));
      b.append(body); b.onclick = () => advance(option.id); choices.append(b);
    }
    if (!visible) choices.append(el('p','muted','当前状态下没有可选分支。请检查条件，或在调试台调整属性与变量。'));
    const hidden = node.options.length - visible;
    if (hidden && !$('show-hidden').checked) choices.append(el('p','muted',`${hidden} 个分支因条件未满足而隐藏。勾选下方“查看不可选分支”可查看。`));
  }
  $('image-area').replaceChildren();
  if (node.image) {
    const path = typeof node.image === 'string' ? node.image : '';
    const p = el('p','muted',`配图：${path || '未识别的图片配置'}`); $('image-area').append(p);
    if (/^https?:\/\//i.test(path)) { const b = el('button','','加载配图'); b.onclick = () => { const img = el('img'); img.alt = '当前剧情配图'; img.referrerPolicy = 'no-referrer'; img.src = path; img.onerror = () => { img.remove(); notify('配图加载失败，请检查图片地址。'); }; $('image-area').append(img); b.remove(); }; $('image-area').append(b); }
    else p.append(document.createTextNode('（本地相对图片路径请在游戏中查看）'));
  }
  renderTrace();
}
function renderNodes() {
  const nodes = story?.nodes && typeof story.nodes === 'object' && !Array.isArray(story.nodes) ? Object.entries(story.nodes) : [];
  $('node-count').textContent = nodes.length; $('nodes').replaceChildren();
  const needle = $('search').value.toLowerCase();
  const visited = new Set(session ? [session.nodeId,...session.history.flatMap(h=>[h.from,h.to])] : []);
  for (const [id,node] of nodes) {
    if (!`${id} ${node?.content || ''}`.toLowerCase().includes(needle)) continue;
    const b = el('button',`node${session?.nodeId === id ? ' active' : ''}${visited.has(id) ? ' visited' : ''}`,id);
    b.append(el('small','',typeof node?.content === 'string' ? node.content : '无正文')); b.disabled = !session;
    b.title = `调试跳转到 ${id}`; b.onclick = () => {
      try { const before = clone(session); const next = R.enterNode(story,session,id); undo.push(before); session = next; notify(`已调试跳转到 ${id}，未执行途中节点效果。`); render(); } catch(error) { notify(error.message); }
    }; $('nodes').append(b);
  }
}
function renderState() {
  $('stats').replaceChildren();
  const player = session?.player || initialPlayer;
  for (const key of ['hp','mp','gold','exp','attack','defense','agility','luck']) {
    const card = el('div','stat'); card.append(el('small','',labels[key]));
    card.append(el('strong','',text(player[key] ?? 0))); if (key === 'hp' || key === 'mp') card.append(el('small','',`上限 ${player[`max_${key}`] ?? '—'}`)); $('stats').append(card);
  }
  $('variables').replaceChildren();
  for (const [key,value] of Object.entries(session?.variables || {})) { const row = el('div','variable'); row.append(el('code','',key),el('span','',text(value))); $('variables').append(row); }
  if (!$('variables').children.length) $('variables').textContent = '暂无剧情变量';
  let trials = player.completed_trials || []; if (typeof trials === 'string') { try { trials = JSON.parse(trials); } catch { trials = []; } }
  $('completed').textContent = Array.isArray(trials) && trials.length ? trials.join('、') : '暂无通关记录';
}
function renderChecks() {
  $('issue-count').textContent = issues.length; $('checks').replaceChildren();
  if (!hasDocument) { $('checks').textContent = '加载剧本后自动检查结构、条件和分支出口。'; return; }
  const errors = issues.filter(i=>i.severity === 'error').length;
  $('checks').append(el('p',errors ? '' : 'success',errors ? `${errors} 个错误需要修正` : '✓ 结构检查通过'));
  if (!errors) $('checks').append(el('p','tip','静态可达不代表所有条件组合都可通关，请继续试跑关键分支。'));
  for (const i of issues) { const row = el('div',`issue ${i.severity}`); row.append(el('code','',i.path),el('span','',i.message)); $('checks').append(row); }
}
function renderTrace() {
  $('trace').replaceChildren();
  if (!session.history.length) { $('trace').textContent = '故事尚未迈出第一步。'; return; }
  session.history.slice().reverse().forEach((item,index) => { const row = el('div','trace-row',`${session.history.length-index}. ${item.label || '继续'}`); row.append(el('small','',`${item.from} → ${item.to || '停留原处'}`)); (item.changes || []).forEach(c=>row.append(el('div','change',typeof c === 'string' ? c : JSON.stringify(c)))); $('trace').append(row); });
}
function recordEdit(label, section, previous, next) {
  const changes = [...new Set([...Object.keys(previous),...Object.keys(next)])].filter(k => JSON.stringify(previous[k]) !== JSON.stringify(next[k])).map(k => `${section}.${k}: ${text(previous[k]) ?? '未设置'} → ${text(next[k]) ?? '已删除'}`);
  session.history.push({from:session.nodeId,to:session.nodeId,label,changes});
}
function advance(optionId=null) { try { const before = clone(session); const next = R.step(story,session,optionId); undo.push(before); session = next; notify(session.lastError || ''); render(); } catch(error) { notify(`无法继续：${error.message}`); } }
function openEditor(mode) {
  editorMode = mode; $('download-story').hidden = mode !== 'story'; $('editor-error').textContent = ''; $('field-editor').hidden = mode !== 'player'; $('json-editor').hidden = mode === 'player';
  $('editor-title').textContent = ({story:'粘贴 / 编辑剧本',player:'调整测试玩家',vars:'编辑剧情变量'})[mode];
  $('editor-help').textContent = ({story:'粘贴完整剧本 JSON。应用后重新检查，并从起点开始。',player:'数值直接填写；文字无需引号；列表和对象使用 JSON。应用会更新当前状态，并作为重新开始时的初始玩家设置。',vars:'以 JSON 对象编辑变量，例如 {"has_key": true}。current_story_id 是固定的剧本标识，不可修改。'})[mode];
  if (mode === 'player') {
    $('field-search').value = ''; $('fields').replaceChildren();
    for (const [key,value] of Object.entries(session.player)) {
      const row = el('label','field'); row.dataset.key = key; const name = el('span','',labels[key] || key); if (labels[key]) name.append(el('small','',key));
      const input = el('input'); input.dataset.key = key; input.dataset.type = value === null ? 'null' : typeof value; input.value = typeof value === 'string' ? value : JSON.stringify(value); input.setAttribute('aria-label',labels[key] || key); row.append(name,input); $('fields').append(row);
    }
  } else $('json-editor').value = mode === 'story' ? raw : JSON.stringify(session.variables,null,2);
  $('editor').showModal();
}
$('editor-form').onsubmit = event => {
  event.preventDefault();
  try {
    if (editorMode === 'story') {
      parseJSON($('json-editor').value); load($('json-editor').value,filename || '粘贴的剧本.json');
    } else if (editorMode === 'vars') {
      const vars = parseJSON($('json-editor').value); if (!vars || typeof vars !== 'object' || Array.isArray(vars)) throw new Error('变量必须是 JSON 对象。');
      if (vars.current_story_id !== story.id) throw new Error('current_story_id 必须保留为当前剧本 ID。');
      undo.push(clone(session)); recordEdit('调试：编辑变量','variables',session.variables,vars); session.variables = vars; notify('剧情变量已更新。'); render();
    } else {
      const player = clone(session.player);
      for (const input of $('fields').querySelectorAll('input')) {
        const key = input.dataset.key, prev = player[key]; let value;
        try { value = input.dataset.type === 'string' ? input.value : parseJSON(input.value); } catch { throw new Error(`${labels[key] || key} 的格式不正确。`); }
        if (prev !== null && (typeof value !== typeof prev || Array.isArray(value) !== Array.isArray(prev) || value === null)) throw new Error(`${labels[key] || key} 的类型不能改变。`);
        if (typeof prev === 'number' && (!Number.isFinite(value) || ((R.playerTypes?.[key] === 'int' || (!R.playerTypes && Number.isInteger(prev))) && !Number.isInteger(value)))) throw new Error(`${labels[key] || key} 需要有效整数。`);
        const declared = R.playerTypes?.[key];
        if (key !== 'completed_trials' && value !== null && declared && !({int:()=>Number.isInteger(value),float:()=>typeof value === 'number' && Number.isFinite(value),str:()=>typeof value === 'string',bool:()=>typeof value === 'boolean',list:()=>Array.isArray(value),dict:()=>typeof value === 'object' && !Array.isArray(value)}[declared]?.() ?? true)) throw new Error(`${labels[key] || key} 的值与字段类型 ${declared} 不符。`);
        if (key === 'completed_trials' && (!Array.isArray(value) || value.some(x=>typeof x !== 'string'))) throw new Error('通关记录必须是字符串列表，例如 ["雾中来信"]。');
        player[key] = value;
      }
      undo.push(clone(session)); recordEdit('调试：调整玩家','player',session.player,player); session.player = player; initialPlayer = clone(player); notify('玩家属性已更新，并保存为本次测试的初始设置。'); render();
    }
    $('editor').close();
  } catch(error) { $('editor-error').textContent = error.message; }
};
$('field-search').oninput = () => { const q = $('field-search').value.toLowerCase(); $('fields').querySelectorAll('.field').forEach(row=>row.hidden = !`${row.dataset.key} ${labels[row.dataset.key] || ''}`.toLowerCase().includes(q)); };
$('open').onclick = $('welcome-open').onclick = () => $('file').click();
$('file').onchange = () => { loadFile($('file').files[0]); $('file').value = ''; };
$('paste').onclick = $('fix-json').onclick = $('edit-source').onclick = () => openEditor('story');
$('edit-player').onclick = () => openEditor('player'); $('edit-vars').onclick = () => openEditor('vars');
$('close-editor').onclick = $('cancel-editor').onclick = () => $('editor').close();
$('download-story').onclick = () => {
  try { const value = parseJSON($('json-editor').value); const url = URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})); const a = el('a'); a.href = url; a.download = filename.endsWith('.json') ? filename : '试炼剧本.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); $('editor-error').textContent = ''; } catch(error) { $('editor-error').textContent = `保存前请修正 JSON 语法：${error.message}`; }
};
$('demo').onclick = () => load(JSON.stringify(demo,null,2),'雾中来信 · 示例.json');
$('show-hidden').onchange = render; $('search').oninput = renderNodes;
$('undo').onclick = () => { if (undo.length) { session = undo.pop(); notify('已恢复上一步的节点、玩家与变量状态。'); render(); } };
$('restart').onclick = () => { try { undo = []; session = R.createSession(story,initialPlayer); notify('已从起点重新开始，使用本次测试的初始玩家设置。'); render(); } catch(error) { notify(error.message); } };
$('export').onclick = () => {
  const report = {story:story.id,filename,exported_at:new Date().toISOString(),mode:'无装备离线模拟',initialPlayer,checks:issues,current:{nodeId:session.nodeId,player:session.player,variables:session.variables,finished:session.finished},history:session.history.map(({before,...rest})=>rest)};
  const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})); const a = el('a'); a.href = url; a.download = '试炼调试记录.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); notify('调试记录已导出。');
};
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick = () => tab(b.dataset.tab));
let dragDepth = 0;
window.addEventListener('dragenter',event=>{ if (event.dataTransfer?.types.includes('Files')) { event.preventDefault(); dragDepth++; $('drop-overlay').hidden = false; } });
window.addEventListener('dragover',event=>{ if (event.dataTransfer?.types.includes('Files')) event.preventDefault(); });
window.addEventListener('dragleave',()=>{ if (--dragDepth <= 0) { dragDepth = 0; $('drop-overlay').hidden = true; } });
window.addEventListener('drop',event=>{ event.preventDefault(); dragDepth = 0; $('drop-overlay').hidden = true; const file = event.dataTransfer?.files[0]; if (file) { if ($('editor').open) $('editor').close(); loadFile(file); } });
render();
})();
