/* Generated from story_debugger.py player_defaults(). */
(function (root) {
"use strict";
const defaults = {
  "nickname": "调试玩家",
  "uid": 1,
  "level": 1,
  "sex": "男",
  "region": "大都会",
  "gold": 1000,
  "hp": 20,
  "max_hp": 20,
  "mp": 20,
  "max_mp": 20,
  "attack": 1,
  "defense": 0,
  "agility": 5,
  "stamina": 10,
  "luck": 1,
  "resentment": 0,
  "exp": 0,
  "vip": 0,
  "completed_trials": [],
  "id": "",
  "server_id": 1,
  "attribute_points": 0,
  "x": 0,
  "y": 0,
  "real_world_x": 0,
  "real_world_y": 0,
  "dungeon_level": 0,
  "dungeon_x": 0,
  "dungeon_y": 0,
  "max_dungeon_level": 0,
  "dungeon_kill_streak": 0,
  "reincarnation_level": 0,
  "breakthrough_fail_count": 0,
  "critical_rate": 5,
  "critical_power": 0,
  "combo_rate": 0,
  "counter_rate": 0,
  "dodge_rate": 0,
  "accuracy_rate": 80,
  "skill_crit_rate": 0,
  "penetration_rate": 0,
  "anti_crit_rate": 0,
  "anti_combo_rate": 0,
  "anti_counter_rate": 0,
  "lifesteal_rate": 0,
  "immobilize_rate": 0,
  "true_damage_rate": 0,
  "regen_rate": 0,
  "total_battles": 0,
  "total_wins": 0,
  "total_damage_dealt": 0,
  "guild_id": null,
  "guild_contribution": 0,
  "gold2": 0,
  "gui_zhu": 0,
  "mini_game_score": 0,
  "demon_coins": 0,
  "charm": 0,
  "prologue_step": 0,
  "last_sign": null,
  "sign_streak": 0,
  "created_at": null,
  "last_cultivation": null,
  "last_active_at": null,
  "fenjin_charge": 0,
  "fenjin_last_update": null,
  "fenjin_last_charge": null,
  "inventory_capacity": 80,
  "inventory_compact": false,
  "is_secluded": false,
  "seclusion_start_time": null,
  "last_message_board_check": null,
  "last_private_message_check": null,
  "last_system_check": null,
  "last_guild_check": null,
  "last_group_openid": null,
  "last_group_member_id": null,
  "last_group_username": null,
  "daily_gift_purchases": null,
  "mansion_level": 0,
  "mansion_x": null,
  "mansion_y": null,
  "mansion_usage_fee": 0,
  "mansion_allow_others": true,
  "mansion_willing_to_pay": true,
  "incense": 0,
  "max_apprentice_slots": 3,
  "mentor_cooldown_until": null,
  "allocated_attrs": null,
  "extra_attrs": {},
  "vip_equipment_data": {},
  "vip_skill_cooldown": {}
};
const playerTypes = {
  "nickname": "str",
  "uid": "int",
  "level": "int",
  "sex": "str",
  "region": "str",
  "gold": "int",
  "hp": "int",
  "max_hp": "int",
  "mp": "int",
  "max_mp": "int",
  "attack": "int",
  "defense": "int",
  "agility": "int",
  "stamina": "int",
  "luck": "int",
  "resentment": "int",
  "exp": "int",
  "vip": "int",
  "completed_trials": "str",
  "id": "str",
  "server_id": "int",
  "attribute_points": "int",
  "x": "int",
  "y": "int",
  "real_world_x": "int",
  "real_world_y": "int",
  "dungeon_level": "int",
  "dungeon_x": "int",
  "dungeon_y": "int",
  "max_dungeon_level": "int",
  "dungeon_kill_streak": "int",
  "reincarnation_level": "int",
  "breakthrough_fail_count": "int",
  "critical_rate": "int",
  "critical_power": "int",
  "combo_rate": "int",
  "counter_rate": "int",
  "dodge_rate": "int",
  "accuracy_rate": "int",
  "skill_crit_rate": "int",
  "penetration_rate": "int",
  "anti_crit_rate": "int",
  "anti_combo_rate": "int",
  "anti_counter_rate": "int",
  "lifesteal_rate": "int",
  "immobilize_rate": "int",
  "true_damage_rate": "int",
  "regen_rate": "int",
  "total_battles": "int",
  "total_wins": "int",
  "total_damage_dealt": "int",
  "guild_id": "int",
  "guild_contribution": "int",
  "gold2": "int",
  "gui_zhu": "int",
  "mini_game_score": "int",
  "demon_coins": "int",
  "charm": "int",
  "prologue_step": "int",
  "sign_streak": "int",
  "fenjin_charge": "float",
  "inventory_capacity": "int",
  "inventory_compact": "bool",
  "is_secluded": "bool",
  "last_group_openid": "str",
  "last_group_member_id": "str",
  "last_group_username": "str",
  "daily_gift_purchases": "str",
  "mansion_level": "int",
  "mansion_x": "int",
  "mansion_y": "int",
  "mansion_usage_fee": "int",
  "mansion_allow_others": "bool",
  "mansion_willing_to_pay": "bool",
  "incense": "int",
  "max_apprentice_slots": "int",
  "allocated_attrs": "dict",
  "extra_attrs": "dict",
  "vip_equipment_data": "dict",
  "vip_skill_cooldown": "dict"
};
const permanentAttributes = ["accuracy_rate", "agility", "anti_combo_rate", "anti_counter_rate", "anti_crit_rate", "attack", "combo_rate", "counter_rate", "critical_power", "critical_rate", "defense", "dodge_rate", "immobilize_rate", "lifesteal_rate", "luck", "max_hp", "max_mp", "penetration_rate", "regen_rate", "skill_crit_rate", "true_damage_rate"];
const own = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
const get = (o, k, fallback = null) => own(o, k) ? o[k] : fallback;
const object = o => o !== null && typeof o === 'object' && !Array.isArray(o) && (Object.getPrototypeOf(o) === Object.prototype || Object.getPrototypeOf(o) === null);
const forbidden = new Set(['__proto__', 'prototype', 'constructor']);
const operators = new Set(['==', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'contains']);
const relative = v => typeof v === 'string' && /^[+-]\d+$/.test(v);
const kind = v => v === null ? 'null' : Array.isArray(v) ? 'list' : object(v) ? 'dict' : typeof v;
const truth = v => Array.isArray(v) ? v.length > 0 : object(v) ? Object.keys(v).length > 0 : Boolean(v);

// Inspect before copying. Reject dangerous keys anywhere, non-JSON values and cycles.
function inspect(value, path, report, ancestors = new Set()) {
    if (value === null || ['string', 'boolean'].includes(typeof value)) return;
    if (typeof value === 'number' && Number.isFinite(value)) return;
    if (!Array.isArray(value) && !object(value)) { report(path, '必须是 JSON 数据'); return; }
    if (ancestors.has(value)) { report(path, 'JSON 数据不能包含循环引用'); return; }
    ancestors.add(value);
    for (const key of Object.keys(value)) {
        if (forbidden.has(key)) report(`${path}.${key}`, '禁止使用可能污染原型的键');
        const descriptor = Object.getOwnPropertyDescriptor(value, key);
        if (!descriptor || !own(descriptor, 'value')) report(`${path}.${key}`, '不允许访问器属性');
        else inspect(descriptor.value, `${path}.${key}`, report, ancestors);
    }
    ancestors.delete(value);
}
function safe(value) {
    inspect(value, '$', (p, m) => { throw new Error(`${p}: ${m}`); });
    return value;
}
function clone(value) { return JSON.parse(JSON.stringify(safe(value))); }
function freeze(value) {
    if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
    return value;
}
freeze(defaults); freeze(playerTypes); freeze(permanentAttributes);
function equal(a, b) {
    if (a === b) return true;
    // Python container equality treats True == 1, while top-level comparisons check types.
    if (['number', 'boolean'].includes(typeof a) && ['number', 'boolean'].includes(typeof b)) return Number(a) === Number(b);
    if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => equal(v, b[i]));
    if (object(a) && object(b)) return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => own(b, k) && equal(a[k], b[k]));
    return false;
}
function member(value, container) {
    if (typeof container === 'string') return typeof value === 'string' ? container.includes(value) : null;
    if (Array.isArray(container)) return container.some(item => equal(item, value));
    if (object(container)) {
        if (Array.isArray(value) || object(value)) return null;
        // JSON object keys are strings; Python does not coerce other key types.
        return typeof value === 'string' && own(container, value);
    }
    return null;
}
function trials(player) {
    let value = get(player, 'completed_trials', []);
    if (typeof value === 'string') { try { value = JSON.parse(value); } catch (e) { if (!(e instanceof SyntaxError)) throw e; return []; } }
    return Array.isArray(value) ? value : [];
}
function compareStrings(a, b) {
    const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
    for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
    return Math.sign(x.length - y.length);
}
function checkValue(value, check) {
    if (value == null || !object(check) || !Object.keys(check).length) return false;
    return Object.entries(check).every(([op, expected]) => {
        if (!operators.has(op)) return false;
        if (['in', 'not_in', 'contains'].includes(op)) {
            const result = op === 'contains' ? member(expected, value) : member(value, expected);
            return result !== null && (op === 'not_in' ? !result : result);
        }
        if (kind(value) !== kind(expected)) return false;
        if (op === '==') return equal(value, expected);
        if (op === '!=') return !equal(value, expected);
        if (!['number', 'string'].includes(typeof value)) return false;
        const order = typeof value === 'string' ? compareStrings(value, expected) : Math.sign(value - expected);
        return op === '>' ? order > 0 : op === '>=' ? order >= 0 : op === '<' ? order < 0 : order <= 0;
    });
}
function evaluateCondition(condition, player, variables) {
    safe(condition); safe(player); safe(variables);
    if (!object(condition) || !object(variables)) return false;
    return Object.entries(condition).every(([key, check]) => {
        if (key === 'and' || key === 'or') {
            if (!Array.isArray(check)) return false;
            const results = check.map(c => evaluateCondition(c, player, variables));
            return key === 'and' ? results.every(Boolean) : results.some(Boolean);
        }
        const value = key.startsWith('player_') ? (key === 'player_completed_trials' ? trials(player) : get(player, key.slice(7))) : get(variables, key.startsWith('story_') ? key.slice(6) : key);
        return checkValue(value, check);
    });
}
function resolveNext(field, player, variables) {
    safe(field); safe(player); safe(variables);
    if (typeof field === 'string') return field;
    if (Array.isArray(field)) for (const branch of field) {
        if (object(branch) && (!own(branch, 'if') || evaluateCondition(branch.if, player, variables))) return typeof branch.goto === 'string' ? branch.goto : null;
    }
    return null;
}
function pyString(value, nested = false) {
    if (value === null) return 'None';
    if (typeof value === 'boolean') return value ? 'True' : 'False';
    if (typeof value === 'string') {
        if (!nested) return value;
        const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
        return quote + value.replace(/\\/g, '\\\\').replace(new RegExp(quote, 'g'), '\\' + quote).replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t') + quote;
    }
    if (Array.isArray(value)) return '[' + value.map(v => pyString(v, true)).join(', ') + ']';
    if (object(value)) return '{' + Object.entries(value).map(([k, v]) => pyString(k, true) + ': ' + pyString(v, true)).join(', ') + '}';
    return String(value);
}
function formatContent(text, player, variables) {
    safe(player); safe(variables);
    if (typeof text !== 'string') return '';
    return text.replace(/\{([^{}]+)\}/g, (match, name) => {
        if (name.startsWith('trial_completed_')) return pyString(trials(player).includes(name.slice(16)));
        if (name.startsWith('player_')) {
            const attr = name.slice(7);
            if (attr === 'x' || attr === 'y') return pyString(get(player, (get(player, 'dungeon_level', 0) > 0 ? 'dungeon_' : 'real_world_') + attr, 0));
            if (attr === 'completed_trials') return pyString(trials(player));
            if (attr === 'name') return pyString(get(player, 'nickname', ''));
            if (attr === 'guild_id') return pyString(truth(get(player, attr)) ? player[attr] : '无');
            return pyString(get(player, attr, ['sex', 'region'].includes(attr) ? '' : 0));
        }
        return own(variables, name) ? pyString(variables[name]) : match;
    });
}

function validate(story) {
    const issues = [];
    const add = (severity, path, message) => issues.push({severity, path, message});
    const error = (p, m) => add('error', p, m), warn = (p, m) => add('warning', p, m);
    inspect(story, '$', error);
    if (issues.length) return issues;
    if (!object(story)) { error('$', '剧情顶层必须是对象'); return issues; }
    const nonempty = v => typeof v === 'string' && v.trim().length > 0;
    for (const k of ['id', 'start_node']) if (!nonempty(story[k])) error(`$.${k}`, '必须是非空字符串');
    for (const k of ['title', 'description']) if (own(story, k) && typeof story[k] !== 'string') error(`$.${k}`, '必须是字符串');
    if (!object(story.nodes) || !Object.keys(story.nodes).length) { error('$.nodes', '必须是非空对象'); return issues; }
    const nodes = story.nodes, graph = new Map(), refs = [];
    if (typeof story.start_node === 'string' && !own(nodes, story.start_node)) error('$.start_node', '起始节点不存在');
    function condition(c, p) {
        if (!object(c)) { error(p, '条件必须是对象'); return; }
        for (const [k, check] of Object.entries(c)) {
            const q = `${p}.${k}`;
            if (k === 'and' || k === 'or') {
                if (!Array.isArray(check)) error(q, '必须是条件列表');
                else { if (!check.length) warn(q, `空 ${k} 恒为 ${k === 'and'}`); check.forEach((x, i) => condition(x, `${q}[${i}]`)); }
                continue;
            }
            if (!object(check) || !Object.keys(check).length) { error(q, '检查必须是非空对象'); continue; }
            if (k.startsWith('player_') && !own(defaults, k.slice(7))) warn(q, '未知玩家属性，条件不会满足');
            for (const [op, v] of Object.entries(check)) {
                if (!operators.has(op)) error(`${q}.${op}`, '无效运算符');
                else if (['in', 'not_in'].includes(op) && !(Array.isArray(v) || object(v) || typeof v === 'string')) error(`${q}.${op}`, '右侧必须是列表、对象或字符串');
                else if (['>', '>=', '<', '<='].includes(op) && !['number', 'string'].includes(typeof v)) error(`${q}.${op}`, '右侧必须是数值或字符串');
                else if (k === 'player_completed_trials' && op === 'contains' && typeof v !== 'string') error(`${q}.${op}`, '通关记录必须指定字符串');
            }
        }
    }
    function jump(field, p, source, execute = true) {
        if (nonempty(field)) { refs.push([field, p]); if (execute) graph.get(source).push(field); return; }
        if (!Array.isArray(field) || !field.length) { error(p, 'next 必须是非空节点ID或条件路由列表'); return; }
        let foundDefault = false;
        field.forEach((branch, i) => {
            const q = `${p}[${i}]`;
            if (!object(branch)) { error(q, '分支必须是对象'); return; }
            if (!nonempty(branch.goto)) error(`${q}.goto`, 'goto 必须是非空节点ID');
            else { refs.push([branch.goto, `${q}.goto`]); if (!foundDefault && execute) graph.get(source).push(branch.goto); }
            if (foundDefault) warn(q, '位于默认分支之后，永远不会执行');
            if (own(branch, 'if')) condition(branch.if, `${q}.if`); else foundDefault = true;
        });
        if (!foundDefault) warn(p, '条件跳转没有默认分支，全部不匹配时执行会报错');
    }
    function effects(e, p, type) {
        if (!object(e)) { error(p, 'effects 必须是对象'); return; }
        for (const [section, changes] of Object.entries(e)) {
            const q = `${p}.${section}`;
            if (!['player', 'variables', 'trial_success', 'first_trial_reward', 'rewards'].includes(section)) { warn(q, '未知 effects 段，游戏不会执行'); continue; }
            if (['trial_success', 'first_trial_reward'].includes(section)) {
                if (typeof changes !== 'boolean') error(q, '必须是布尔值');
                if (section === 'first_trial_reward' && changes) warn(q, '已下架，不会给予奖励');
            } else if (!object(changes)) error(q, '必须是对象');
            else if (section !== 'rewards') for (const [k, v] of Object.entries(changes)) {
                const r = `${q}.${k}`;
                if (typeof v === 'string' && /^[+-]/.test(v) && !relative(v)) error(r, '相对变化必须是带正负号的整数');
                if (section === 'player') {
                    if (!own(defaults, k)) { error(r, '未知玩家属性'); continue; }
                    const t = get(playerTypes, k);
                    if (['int', 'float'].includes(t)) {
                        if (!(relative(v) || (typeof v === 'number' && (t === 'float' || Number.isInteger(v))))) error(r, '必须是数值或整数相对变化');
                    } else if (relative(v)) error(r, '非数值属性不能相对变化');
                    else if (['str', 'bool', 'dict', 'list'].includes(t) && !(v === null && defaults[k] === null) && kind(v) !== {str:'string', bool:'boolean', dict:'dict', list:'list'}[t]) error(r, '属性类型不符');
                }
            }
        }
        if (type === 'choice' && Object.keys(e).length) warn(p, 'choice 节点自身 effects 不执行');
        if (type === 'end' && (own(e, 'player') || own(e, 'variables'))) warn(p, 'end 仅处理特殊效果，不执行 player/variables');
        if (type === 'story' && (own(e, 'trial_success') || own(e, 'first_trial_reward'))) warn(p, '普通节点不处理通关特殊效果');
        if (type === 'option' && ['trial_success', 'first_trial_reward', 'rewards'].some(k => own(e, k))) warn(p, '特殊通关效果和奖励仅在 end 处理');
    }
    for (const id of Object.keys(nodes)) graph.set(id, []);
    for (const [id, node] of Object.entries(nodes)) {
        const p = `$.nodes.${id}`;
        if (!nonempty(id)) error(p, '节点ID必须是非空字符串');
        if (!object(node)) { error(p, '节点必须是对象，条件路由应放入 next'); continue; }
        if (!['story', 'choice', 'end'].includes(node.type)) error(`${p}.type`, '必须为 story、choice 或 end');
        if (own(node, 'content') && typeof node.content !== 'string') error(`${p}.content`, '必须是字符串');
        else if (!own(node, 'content') && node.type !== 'end') warn(`${p}.content`, '缺少 content');
        if (own(node, 'image') && !nonempty(node.image)) error(`${p}.image`, '必须是非空字符串');
        if (own(node, 'effects')) effects(node.effects, `${p}.effects`, node.type);
        if (node.type === 'story') {
            if (own(node, 'options')) error(`${p}.options`, 'story 不能使用 options');
            jump(node.next, `${p}.next`, id);
        } else if (own(node, 'next')) { warn(`${p}.next`, '该节点自身 next 不执行'); jump(node.next, `${p}.next`, id, false); }
        if (node.type === 'choice' && (!Array.isArray(node.options) || !node.options.length)) error(`${p}.options`, '必须是非空列表');
        if (own(node, 'options') && !Array.isArray(node.options)) error(`${p}.options`, '必须是列表');
        if (node.type === 'end' && own(node, 'options')) warn(`${p}.options`, 'end 的 options 不执行');
        const ids = new Set();
        if (Array.isArray(node.options)) node.options.forEach((option, i) => {
            const q = `${p}.options[${i}]`;
            if (!object(option)) { error(q, '选项必须是对象'); return; }
            if (!Number.isInteger(option.id) || option.id < 1 || option.id > 9) error(`${q}.id`, '必须是 1—9 的整数');
            else if (ids.has(option.id)) error(`${q}.id`, '选项ID重复');
            ids.add(option.id);
            if (!nonempty(option.text)) error(`${q}.text`, '必须是非空字符串');
            if (own(option, 'conditions')) condition(option.conditions, `${q}.conditions`);
            if (own(option, 'effects')) effects(option.effects, `${q}.effects`, 'option');
            jump(option.next, `${q}.next`, id, node.type === 'choice');
        });
    }
    for (const [target, p] of refs) if (!own(nodes, target)) error(p, `引用的节点不存在: ${target}`);
    if (own(nodes, story.start_node)) {
        const reachable = new Set(), queue = [story.start_node];
        for (let i = 0; i < queue.length; i++) {
            const id = queue[i]; if (reachable.has(id) || !own(nodes, id)) continue;
            reachable.add(id); queue.push(...graph.get(id));
        }
        for (const id of Object.keys(nodes)) if (!reachable.has(id)) warn(`$.nodes.${id}`, '不可达节点');
        const ends = [...reachable].filter(id => get(nodes[id], 'type') === 'end');
        if (!ends.length) error('$.start_node', '无法到达任何结束节点');
        const reverse = new Map(Object.keys(nodes).map(id => [id, []]));
        for (const [source, targets] of graph) for (const target of targets) if (reverse.has(target)) reverse.get(target).push(source);
        const canFinish = new Set(), pending = [...ends];
        for (let i = 0; i < pending.length; i++) { const id = pending[i]; if (canFinish.has(id)) continue; canFinish.add(id); pending.push(...reverse.get(id)); }
        for (const id of reachable) if (!canFinish.has(id)) error(`$.nodes.${id}`, '可达节点无法到达结局（无出口循环或断路）');
    }
    return issues;
}
function assertStory(story) {
    const errors = validate(story).filter(i => i.severity === 'error');
    if (errors.length) throw new Error(errors.map(i => `${i.path}: ${i.message}`).join('\n'));
}
function applyChanges(changes, state) {
    for (const [key, change] of Object.entries(changes)) {
        if (relative(change)) {
            const old = get(state, key, 0);
            if (!['number', 'boolean'].includes(typeof old)) throw new Error(`无法对 ${key} 执行数值相对变化`);
            const value = Number(old) + Number(change);
            if (!Number.isFinite(value)) throw new Error(`数值溢出: ${key}`);
            state[key] = value;
        } else state[key] = clone(change);
    }
}
function applyEffects(effects, session) {
    const before = clone(session.player);
    applyChanges(get(effects, 'player', {}), session.player);
    applyChanges(get(effects, 'variables', {}), session.variables);
    if (permanentAttributes.some(k => !equal(before[k], session.player[k]))) {
        for (const [k, max] of [['hp', 'max_hp'], ['mp', 'max_mp']]) {
            if (typeof session.player[k] !== 'number' || typeof session.player[max] !== 'number') throw new Error('血量/理智上限必须是数值');
            session.player[k] = Math.min(session.player[k], session.player[max]);
        }
    }
}
function settle(story, session, nodeId) {
    if (!own(story.nodes, nodeId)) throw new Error(`跳转目标不存在: ${nodeId}`);
    session.nodeId = nodeId;
    session.finished = story.nodes[nodeId].type === 'end';
    if (session.finished) {
        const effects = get(story.nodes[nodeId], 'effects', {});
        const storyId = get(session.variables, 'current_story_id', '');
        if (truth(get(effects, 'trial_success', false)) && truth(storyId)) {
            const trialId = storyId + (truth(get(session.variables, 'perfect_ending', false)) ? '_完美' : '');
            const completed = clone(trials(session.player));
            if (!completed.includes(trialId)) { completed.push(trialId); session.player.completed_trials = completed; }
        }
    }
}
function snapshot(session) {
    return clone({player:session.player, variables:session.variables, nodeId:session.nodeId, finished:session.finished});
}
function trace(session, before, label) {
    const changes = [];
    for (const area of ['player', 'variables']) for (const key of new Set([...Object.keys(before[area]), ...Object.keys(session[area])])) {
        if (!own(before[area], key) || !equal(before[area][key], session[area][key])) changes.push(`${area}.${key}: ${own(before[area], key) ? pyString(before[area][key]) : '未设置'} → ${pyString(session[area][key])}`);
    }
    session.history.push({from:before.nodeId, to:session.nodeId, label, changes, before});
}
function createSession(story, initialPlayer = defaults) {
    assertStory(story); safe(initialPlayer);
    if (!object(initialPlayer)) throw new Error('initialPlayer 必须是对象');
    const player = clone(defaults);
    for (const [key, value] of Object.entries(initialPlayer)) {
        if (!own(defaults, key)) throw new Error(`未知玩家属性: ${key}`);
        const t = get(playerTypes, key);
        const valid = key === 'completed_trials' ? (Array.isArray(value) && value.every(v => typeof v === 'string')) || (typeof value === 'string' && (() => { try { const a = JSON.parse(value); return Array.isArray(a) && a.every(v => typeof v === 'string'); } catch (e) { return false; } })())
            : value === null ? defaults[key] === null
            : t === 'int' ? typeof value === 'number' && Number.isInteger(value)
            : t === 'float' ? typeof value === 'number'
            : t ? kind(value) === {str:'string', bool:'boolean', dict:'dict', list:'list'}[t] : true;
        if (!valid) throw new Error(`玩家属性类型不符: ${key}`);
        player[key] = clone(value);
    }
    const session = {player, variables:{current_story_id:story.id}, nodeId:story.start_node, finished:false, history:[]};
    settle(story, session, session.nodeId);
    return session;
}
function enterNode(story, session, nodeId) {
    assertStory(story);
    if (typeof nodeId !== 'string') throw new Error('nodeId 必须是字符串');
    const result = clone(session), before = snapshot(session);
    delete result.lastError;
    settle(story, result, nodeId);
    trace(result, before, '调试跳转');
    return result;
}
function visibleOptions(node, player, variables) {
    safe(node); safe(player); safe(variables);
    return object(node) && Array.isArray(node.options) ? node.options.filter(o => object(o) && (!own(o, 'conditions') || evaluateCondition(o.conditions, player, variables))) : [];
}
function step(story, session, optionId = null) {
    assertStory(story); safe(session);
    if (session.finished) throw new Error('试炼已经结束');
    if (!own(story.nodes, session.nodeId)) throw new Error('当前节点不存在');
    const node = story.nodes[session.nodeId];
    let action, label;
    if (node.type === 'story') {
        if (optionId !== null) throw new Error('story 节点不能选择选项');
        action = node; label = '继续';
    } else if (node.type === 'choice') {
        action = node.options.find(o => o.id === optionId);
        if (!action) throw new Error(`选项不存在: ${optionId}`);
        if (!evaluateCondition(get(action, 'conditions', {}), session.player, session.variables)) throw new Error('不满足选择条件');
        label = action.text;
    } else throw new Error('结束节点不能继续');
    const result = clone(session), before = snapshot(session);
    delete result.lastError;
    applyEffects(get(action, 'effects', {}), result);
    const target = resolveNext(action.next, result.player, result.variables);
    if (!target) result.lastError = '没有匹配的跳转路由；效果已应用，当前节点未推进。请检查路由条件，重复继续会再次应用效果。';
    else settle(story, result, target);
    trace(result, before, label);
    return result;
}
const api = {defaults, playerTypes, permanentAttributes, validate, evaluateCondition, resolveNext, formatContent, createSession, step, enterNode, visibleOptions};
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (root) root.StoryWebRuntime = api;
})(typeof window !== 'undefined' ? window : null);
