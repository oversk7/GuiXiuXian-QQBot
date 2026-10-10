'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const runtimePath = path.resolve(__dirname, '../plugins/xiuxian_game/story/web_debugger/runtime.js');
const R = require(runtimePath);
const storyDir = path.resolve(__dirname, '../plugins/xiuxian_game/data/stories');
const copy = v => JSON.parse(JSON.stringify(v));
const story = () => ({id:'test', start_node:'s', nodes:{s:{type:'story', content:'开始', next:'c', effects:{player:{gold:'+5'}, variables:{score:1}}}, c:{type:'choice', content:'选择', options:[{id:1, text:'完成', next:'e', effects:{variables:{perfect_ending:true}}}]}, e:{type:'end', content:'结束', effects:{trial_success:true}}}});
const errors = s => R.validate(s).filter(i => i.severity === 'error');

test('ordinary browser script exposes identical API without require', () => {
    const context = vm.createContext({window:{}});
    vm.runInContext(fs.readFileSync(runtimePath, 'utf8'), context);
    const browser = context.window.StoryWebRuntime;
    assert.deepEqual(Object.keys(browser), Object.keys(R));
    const result = vm.runInContext(`window.StoryWebRuntime.createSession(${JSON.stringify(story())})`, context);
    assert.equal(result.nodeId, 's');
    assert.equal(result.player.gold, 1000);
});

test('all seven real stories pass strict validation', () => {
    const files = fs.readdirSync(storyDir).filter(f => f.endsWith('.json'));
    assert.equal(files.length, 7);
    for (const f of files) {
        const s = JSON.parse(fs.readFileSync(path.join(storyDir, f), 'utf8').replace(/^\uFEFF/, ''));
        assert.deepEqual(errors(s), [], f);
        const session = R.createSession(s);
        assert.equal(session.nodeId, s.start_node);
        assert.equal(session.variables.current_story_id, s.id);
        for (const id of Object.keys(s.nodes)) {
            const jumped = R.enterNode(s, session, id);
            assert.equal(jumped.finished, s.nodes[id].type === 'end');
        }
    }
});

test('defaults, field types and permanent attribute set exactly match Python debugger', () => {
    const source = "import importlib.util,json; s=importlib.util.spec_from_file_location('d','plugins/xiuxian_game/story/story_debugger.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps({'defaults':m.PLAYER_DEFAULTS,'types':{k:v.__name__ for k,v in m.PLAYER_ATTRIBUTE_TYPES.items()},'permanent':sorted(m.PERMANENT_ATTRIBUTES)},ensure_ascii=False))";
    const run = spawnSync('python', ['-c', source], {cwd:path.resolve(__dirname, '..'), encoding:'utf8', env:{...process.env, PYTHONIOENCODING:'utf-8'}});
    assert.equal(run.status, 0, run.stderr);
    const expected = JSON.parse(run.stdout);
    assert.deepEqual(R.defaults, expected.defaults);
    assert.deepEqual(R.playerTypes, expected.types);
    assert.deepEqual(R.permanentAttributes, expected.permanent);
});

test('conditions: all sibling entries AND, aliases, empty logical lists and type checks', () => {
    const p = {...R.defaults, gold:10, completed_trials:'["first"]'};
    const v = {score:3, text:'abc', array:[1, {x:2}], obj:{key:0}, yes:true};
    const cases = [
        [{}, true], [null, false], [[], false],
        [{and:[]}, true], [{or:[]}, false],
        [{or:[{score:{'==':3}}, {score:{'==':4}}], player_gold:{'>':11}}, false],
        [{and:[{story_score:{'>=':3}}, {score:{'<':4}}], text:{contains:'b'}}, true],
        [{player_gold:{'>=':10, '<=':10, '!=':9}}, true],
        [{player_gold:{'==':'10'}}, false], [{player_gold:{'!=':'10'}}, false],
        [{yes:{'==':1}}, false], [{yes:{'>':false}}, false],
        [{text:{in:'zabc'}}, true], [{text:{not_in:['z']}}, true],
        [{score:{in:3}}, false], [{score:{not_in:3}}, false],
        [{array:{contains:{x:2}}}, true], [{obj:{contains:'key'}}, true],
        [{score:{in:{3:0}}}, false], [{text:{'??':1}}, false],
        [{player_missing:{'!=':0}}, false], [{player_completed_trials:{contains:'first'}}, true],
        [{score:{}}, false], [{and:{}}, false], [{or:[null, {}]}, true],
        [{text:{'>':'abb'}}, true], [{array:{'==':[true,{x:2}]}}, true]
    ];
    for (const [c, expected] of cases) assert.equal(R.evaluateCondition(c, p, v), expected, JSON.stringify(c));
    assert.equal(R.evaluateCondition({}, p, null), false);
    assert.equal(R.evaluateCondition({player_completed_trials:{contains:'first'}}, {...p,completed_trials:'invalid'}, v), false);
    assert.equal(R.evaluateCondition({a:{'>':'\uE000'}}, p, {a:'\u{10000}'}), true, 'Python Unicode codepoint ordering');
});

test('routing uses first satisfied/default branch and formatting follows Python', () => {
    const p = {...R.defaults, nickname:'玩家', guild_id:0, real_world_x:7, real_world_y:8, dungeon_x:2, dungeon_y:3, completed_trials:['first']};
    const v = {score:2, yes:true, nothing:null, list:['a',false], obj:{a:1}};
    const routes = [{if:{score:{'>':5}}, goto:'bad'}, {if:{score:{'==':2}}, goto:'good'}, {goto:'fallback'}];
    assert.equal(R.resolveNext(routes,p,v), 'good');
    assert.equal(R.resolveNext([{goto:'first'}, {goto:'second'}],p,v), 'first');
    assert.equal(R.resolveNext([{if:{score:{'>':9}},goto:'none'}],p,v), null);
    assert.equal(R.resolveNext('direct',p,v), 'direct');
    assert.equal(R.resolveNext(null,p,v), null);
    assert.equal(R.resolveNext([{}, {goto:'later'}],p,v), null);
    assert.equal(R.formatContent('{player_name}/{player_x},{player_y}/{player_guild_id}/{player_completed_trials}/{trial_completed_first}/{trial_completed_other}/{yes}/{nothing}/{list}/{obj}/{missing}/{story_score}/{player_unknown}',p,v), "玩家/7,8/无/['first']/True/False/True/None/['a', False]/{'a': 1}/{missing}/{story_score}/0");
    assert.equal(R.formatContent('{player_x},{player_y}', {...p,dungeon_level:1},v),'2,3');
    assert.equal(R.formatContent(null,p,v),'');
});

test('effects occur on continue and selected option, then end only records success', () => {
    const s = story();
    s.nodes.c.effects = {player:{gold:'+100'}, variables:{ignored:true}};
    s.nodes.c.options[0].effects.player = {hp:99, max_hp:15, mp:99, attack:'+1'};
    s.nodes.c.options[0].next = [{if:{perfect_ending:{'==':true}, player_gold:{'==':1005}},goto:'e'}];
    s.nodes.e.effects = {player:{gold:'+999'}, variables:{ignored:true}, trial_success:true, first_trial_reward:true, rewards:{gold:500}};
    const initial = R.createSession(s);
    assert.equal(initial.player.gold, 1000);
    const started = R.step(s, initial);
    assert.equal(started.player.gold,1005);
    assert.equal(started.variables.score,1);
    assert.equal(started.variables.ignored,undefined);
    assert.equal(initial.nodeId,'s');
    const final = R.step(s, started,1);
    assert.equal(final.finished,true);
    assert.equal(final.player.gold,1005);
    assert.equal(final.player.hp,15);
    assert.equal(final.player.mp,20);
    assert.deepEqual(final.player.completed_trials,['test_完美']);
    assert.equal(final.variables.ignored,undefined);
    assert.equal(final.history.length,2);
    assert.equal(final.history[1].label,'完成');
    assert.deepEqual(final.history[1].before.player,started.player);
    assert.deepEqual(Object.keys(final.history[1].before).sort(), ['finished','nodeId','player','variables']);
    assert.ok(final.history[1].changes.every(x => typeof x === 'string'));
    assert.ok(final.history[1].changes.some(x => x.includes('completed_trials')));
    assert.equal(final.history[1].from,'c'); assert.equal(final.history[1].to,'e');
    final.history[0].before.player.gold = 0;
    assert.equal(initial.player.gold,1000);
    assert.equal(started.history[0].before.player.gold,1000);
    assert.throws(() => R.step(s,final), /已经结束/);
});

test('cap requires actual permanent change; ordinary relative vars default to zero', () => {
    const s = story();
    s.nodes.s.effects = {player:{hp:90, mp:80, attack:'+0'}, variables:{count:'+3', debt:'-2', list:[1]}};
    let session = R.step(s,R.createSession(s));
    assert.equal(session.player.hp,90); assert.equal(session.player.mp,80);
    assert.equal(session.variables.count,3); assert.equal(session.variables.debt,-2);
    s.nodes.c.options[0].effects = {player:{accuracy_rate:'+1'}};
    session = R.step(s,session,1);
    assert.equal(session.player.hp,20); assert.equal(session.player.mp,20);
});

test('debug jump and initial end settle once, no node ordinary effects applied', () => {
    const s = story();
    s.nodes.e.effects.player = {gold:'+99'};
    const a = R.createSession(s);
    const b = R.enterNode(s,a,'e');
    assert.equal(b.finished,true); assert.equal(b.player.gold,1000);
    assert.deepEqual(b.player.completed_trials,['test']);
    const c = R.enterNode(s,b,'e');
    assert.deepEqual(c.player.completed_trials,['test']);
    assert.equal(c.history.length,2);
    assert.equal(c.history[1].label,'调试跳转');
    const d = R.enterNode(s,c,'s');
    assert.equal(d.finished,false); assert.equal(d.player.gold,1000);
    assert.throws(() => R.enterNode(s,a,'unknown'), /不存在/);
    assert.deepEqual(a.history,[]);
    s.start_node = 'e';
    const first = R.createSession(s);
    assert.equal(first.finished,true); assert.deepEqual(first.player.completed_trials,['test']);
    assert.deepEqual(first.history,[]);
});

test('missing routes preserve applied effects like engine; effect failures and invalid choices are atomic', () => {
    const s = story();
    s.nodes.s.next = [{if:{player_gold:{'>':9999}},goto:'c'}];
    const a = R.createSession(s), before = copy(a);
    const stopped = R.step(s,a);
    assert.match(stopped.lastError, /没有匹配/);
    assert.equal(stopped.nodeId,a.nodeId);
    assert.equal(stopped.player.gold,a.player.gold+5);
    assert.equal(stopped.variables.score,1);
    assert.equal(stopped.history.length,1);
    assert.deepEqual(a,before);
    s.nodes.s.next = 'c';
    const b = R.step(s,a);
    s.nodes.c.options[0].conditions = {player_gold:{'>':9999}};
    assert.deepEqual(R.visibleOptions(s.nodes.c,b.player,b.variables),[]);
    assert.throws(() => R.step(s,b,1), /不满足/);
    assert.throws(() => R.step(s,b,'1'), /不存在/);
    assert.throws(() => R.step(s,b), /不存在/);
    assert.throws(() => R.step(s,a,1), /不能选择/);
    delete s.nodes.c.options[0].conditions;
    s.nodes.c.options[0].effects = {variables:{score:'+1'}};
    b.variables.score = 'text';
    const bBefore = copy(b);
    assert.throws(() => R.step(s,b,1), /相对变化/);
    assert.deepEqual(b,bBefore);
});

test('strict validation rejects structural, condition, effect and reference errors', () => {
    const cases = [
        null, [], {}, {id:'x',start_node:'s',nodes:[]},
        s => { s.nodes.s = []; },
        s => { s.nodes.s.type = 'route'; },
        s => { s.nodes.s.content = 1; },
        s => { s.nodes.s.options = []; },
        s => { s.nodes.s.next = []; },
        s => { s.nodes.s.next = [{goto:1,if:null}]; },
        s => { s.nodes.c.options = []; },
        s => { s.nodes.c.options[0].id = true; },
        s => { s.nodes.c.options.push(copy(s.nodes.c.options[0])); },
        s => { s.nodes.c.options[0].text = ''; },
        s => { s.nodes.c.options[0].conditions = {and:{}}; },
        s => { s.nodes.c.options[0].conditions = {x:{bogus:0}}; },
        s => { s.nodes.c.options[0].conditions = {x:{in:3}}; },
        s => { s.nodes.c.options[0].conditions = {x:{'>':true}}; },
        s => { s.nodes.c.options[0].conditions = {player_completed_trials:{contains:1}}; },
        s => { s.nodes.s.effects = []; },
        s => { s.nodes.s.effects = {trial_success:1}; },
        s => { s.nodes.s.effects = {variables:[]}; },
        s => { s.nodes.s.effects = {variables:{a:'+1.2'}}; },
        s => { s.nodes.s.effects = {player:{unknown:1}}; },
        s => { s.nodes.s.effects = {player:{hp:1.5}}; },
        s => { s.nodes.s.effects = {player:{inventory_compact:1}}; },
        s => { s.nodes.s.effects = {player:{nickname:'+1'}}; },
        s => { s.nodes.s.next = 'absent'; },
        s => { s.nodes.s.next = [{goto:'c'}, {goto:'absent'}]; }
    ];
    for (const entry of cases) {
        const candidate = typeof entry === 'function' ? story() : entry;
        if (typeof entry === 'function') entry(candidate);
        const list = R.validate(candidate);
        assert.ok(list.some(i => i.severity === 'error'), String(entry));
        assert.ok(list.every(i => typeof i.path === 'string' && typeof i.message === 'string' && ['error','warning'].includes(i.severity)));
        assert.throws(() => R.createSession(candidate), Error);
    }
});

test('graph catches reachable dead loops, ignores routes after default, warns unreachable', () => {
    const s = story();
    s.nodes.loop = {type:'story', next:'loop'};
    s.nodes.c.options.push({id:2,text:'死路',next:'loop'});
    assert.ok(errors(s).some(i => i.path.endsWith('loop') && i.message.includes('无法到达')));
    s.nodes.c.options.pop();
    s.nodes.s.next = [{goto:'c'}, {goto:'loop'}];
    assert.deepEqual(errors(s),[]);
    assert.ok(R.validate(s).some(i => i.severity === 'warning' && i.message.includes('不可达')));
    s.nodes.c.options[0].next = 's';
    assert.ok(errors(s).some(i => i.message.includes('无法到达任何结束')));
});

test('shared runtime results match Python for condition, route and formatting fixtures', () => {
    const fixtures = {
        player:{...R.defaults, gold:10, completed_trials:'["first"]', real_world_x:2, real_world_y:4},
        variables:{score:3, text:'abc', yes:true, list:[1,false], obj:{key:2}},
        conditions:[{},null,[],{and:[]},{or:[]},{or:[{score:{'==':3}}],player_gold:{'>':20}},
            {story_score:{'>=':3,'<':4}},{player_gold:{'!=':'10'}},{yes:{'==':1}},
            {list:{contains:true}},{obj:{contains:'key'}},{score:{not_in:4}},
            {player_completed_trials:{contains:'first'}},{text:{in:'abcde'}},
            {list:{'==':[true,0]}},{obj:{'==':{key:2}}}],
        routes:['s',null,[{if:{score:{'>':10}},goto:'no'},{goto:'yes'}], [{if:{score:{'>':10}},goto:'no'}]],
        texts:['{player_name}/{player_x}/{player_y}/{player_guild_id}/{trial_completed_first}', '{list}/{obj}/{yes}/{missing}/{story_score}/{player_unknown}']
    };
    const source = [
        'import importlib.util,json,sys',
        "s=importlib.util.spec_from_file_location('d','plugins/xiuxian_game/story/story_debugger.py')",
        'm=importlib.util.module_from_spec(s); s.loader.exec_module(m)',
        'f=json.load(sys.stdin); r=m.runtime.StoryRuntime(); p=m.OfflinePlayer(f["player"]); v=f["variables"]',
        'print(json.dumps({"conditions":[r.evaluate_condition(c,p,v) for c in f["conditions"]],"routes":[r.resolve_next(c,p,v) for c in f["routes"]],"texts":[r.format_content(c,p,v) for c in f["texts"]]},ensure_ascii=False))'
    ].join('\n');
    const run = spawnSync('python',['-c',source],{cwd:path.resolve(__dirname,'..'),encoding:'utf8',input:JSON.stringify(fixtures),env:{...process.env,PYTHONIOENCODING:'utf-8'}});
    assert.equal(run.status,0,run.stderr);
    const actual = {
        conditions:fixtures.conditions.map(c => R.evaluateCondition(c,fixtures.player,fixtures.variables)),
        routes:fixtures.routes.map(c => R.resolveNext(c,fixtures.player,fixtures.variables)),
        texts:fixtures.texts.map(c => R.formatContent(c,fixtures.player,fixtures.variables))
    };
    assert.deepEqual(actual,JSON.parse(run.stdout));
});

test('untrusted JSON cannot poison prototypes, including nested effects and overrides', () => {
    for (const key of ['__proto__','constructor','prototype']) {
        const s = story();
        s.nodes.s.effects.variables = JSON.parse(`{"${key}":{"polluted":true}}`);
        assert.ok(errors(s).some(i => i.message.includes('原型')));
        assert.throws(() => R.createSession(s), /原型/);
        assert.throws(() => R.createSession(story(),JSON.parse(`{"${key}":{}}`)), /原型/);
        assert.throws(() => R.evaluateCondition(JSON.parse(`{"${key}":{}}`),R.defaults,{}), /原型/);
    }
    const cyclic = story(); cyclic.nodes.s.effects.variables = cyclic;
    assert.ok(errors(cyclic).some(i => i.message.includes('循环')));
    const s = story(); let accessed = false;
    Object.defineProperty(s,'title',{enumerable:true,get(){accessed=true; return 'x';}});
    assert.ok(errors(s).some(i => i.message.includes('访问器')));
    assert.equal(accessed,false);
    assert.equal({}.polluted,undefined);
    assert.throws(() => R.createSession(story(),{gold:true}), /类型/);
    assert.throws(() => R.createSession(story(),{unknown:1}), /未知/);
    const a = R.createSession(story(),{completed_trials:['old'],guild_id:null});
    a.player.extra_attrs.x = 1;
    assert.deepEqual(R.defaults.extra_attrs,{});
});
