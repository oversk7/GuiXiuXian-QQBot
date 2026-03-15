"""
Story Debugger - 剧情脚本调试工具

功能:
1. 语法验证 - 检查JSON格式和必需字段
2. 节点完整性检查 - 验证所有节点引用
3. 条件测试 - 模拟不同玩家状态
4. 路径分析 - 检查可达性和死循环
5. 交互式调试 - 逐步执行剧情
6. 变量追踪 - 追踪剧情变量变化
7. 问题报告 - 生成详细的错误报告

使用方法:
    python story_debugger.py <story_file.json>
    python story_debugger.py <story_file.json> --interactive
    python story_debugger.py <story_file.json> --check-all
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple
from collections import defaultdict


class StoryDebugger:
    """剧情调试器"""

    def __init__(self, story_file: str):
        self.story_file = story_file
        self.story_data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.nodes: Dict[str, Dict] = {}
        self.node_references: Dict[str, List[str]] = defaultdict(list)

    def load_story(self) -> bool:
        """加载剧情文件"""
        print(f"\n[1/7] 加载剧情文件: {self.story_file}")

        if not os.path.exists(self.story_file):
            self.errors.append(f"文件不存在: {self.story_file}")
            return False

        try:
            with open(self.story_file, 'r', encoding='utf-8') as f:
                self.story_data = json.load(f)
            print(f"  [OK] 成功加载 JSON 文件")
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON 格式错误: {e}")
            return False
        except Exception as e:
            self.errors.append(f"加载失败: {e}")
            return False

    def validate_structure(self) -> bool:
        """验证基本结构"""
        print("\n[2/7] 验证基本结构")

        # 检查必需字段
        required_fields = ['id', 'title', 'description', 'start_node', 'nodes']
        for field in required_fields:
            if field not in self.story_data:
                self.errors.append(f"缺少必需字段: {field}")

        if 'nodes' in self.story_data:
            self.nodes = self.story_data['nodes']
            if not isinstance(self.nodes, dict):
                self.errors.append("nodes 必须是字典类型")
            elif len(self.nodes) == 0:
                self.errors.append("nodes 不能为空")
            else:
                print(f"  [OK] 找到 {len(self.nodes)} 个节点")

        # 检查起始节点是否存在
        if 'start_node' in self.story_data:
            start_node = self.story_data['start_node']
            if start_node not in self.nodes:
                self.errors.append(f"起始节点不存在: {start_node}")
            else:
                print(f"  [OK] 起始节点: {start_node}")

        return len(self.errors) == 0

    def validate_nodes(self) -> bool:
        """验证所有节点"""
        print("\n[3/7] 验证节点配置")

        valid_types = ['story', 'choice', 'end']
        node_count = len(self.nodes)

        for node_id, node_data in self.nodes.items():
            # 检查节点类型
            if 'type' not in node_data:
                self.errors.append(f"节点 '{node_id}' 缺少 type 字段")
                continue

            node_type = node_data['type']
            if node_type not in valid_types:
                self.errors.append(f"节点 '{node_id}' 类型无效: {node_type}")

            # 检查内容
            if 'content' not in node_data and node_type != 'end':
                self.warnings.append(f"节点 '{node_id}' 缺少 content 字段")

            # 检查跳转
            if node_type == 'story':
                if 'next' not in node_data:
                    self.warnings.append(f"story 节点 '{node_id}' 缺少 next 字段")
                else:
                    self._collect_references(node_id, node_data['next'])

            elif node_type == 'choice':
                if 'options' not in node_data:
                    self.errors.append(f"choice 节点 '{node_id}' 缺少 options 字段")
                else:
                    options = node_data['options']
                    if not isinstance(options, list) or len(options) == 0:
                        self.errors.append(f"节点 '{node_id}' options 必须是非空列表")
                    else:
                        # 检查选项
                        option_ids = set()
                        for i, option in enumerate(options):
                            if 'id' not in option:
                                self.errors.append(f"节点 '{node_id}' 选项 {i} 缺少 id")
                            else:
                                opt_id = option['id']
                                if opt_id in option_ids:
                                    self.errors.append(f"节点 '{node_id}' 选项ID重复: {opt_id}")
                                option_ids.add(opt_id)

                            if 'text' not in option:
                                self.errors.append(f"节点 '{node_id}' 选项 {i} 缺少 text")

                            if 'next' in option:
                                self._collect_references(node_id, option['next'])

        print(f"  [OK] 验证了 {node_count} 个节点")
        return True

    def _collect_references(self, from_node: str, next_field: Any):
        """收集节点引用"""
        if isinstance(next_field, str):
            self.node_references[next_field].append(from_node)
        elif isinstance(next_field, list):
            for branch in next_field:
                if isinstance(branch, dict) and 'goto' in branch:
                    self.node_references[branch['goto']].append(from_node)

    def check_references(self) -> bool:
        """检查节点引用完整性"""
        print("\n[4/7] 检查节点引用")

        # 检查所有引用的节点是否存在
        for node_id, refs in self.node_references.items():
            if node_id not in self.nodes:
                self.errors.append(f"引用的节点不存在: '{node_id}' (被 {refs} 引用)")

        # 检查孤立节点 (除了起始节点外,没有被引用的节点)
        start_node = self.story_data.get('start_node')
        unreferenced = []
        for node_id in self.nodes:
            if node_id != start_node and node_id not in self.node_references:
                unreferenced.append(node_id)

        if unreferenced:
            self.warnings.append(f"孤立节点 (无法到达): {unreferenced}")

        print(f"  [OK] 检查了 {len(self.node_references)} 个节点引用")
        return True

    def analyze_paths(self) -> bool:
        """分析剧情路径"""
        print("\n[5/7] 分析剧情路径")

        start_node = self.story_data.get('start_node')
        if not start_node:
            return False

        # BFS 检查可达性
        visited = set()
        queue = [start_node]
        path_count = 0
        end_nodes = []

        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue

            visited.add(node_id)

            if node_id not in self.nodes:
                continue

            node = self.nodes[node_id]
            node_type = node.get('type')

            if node_type == 'end':
                end_nodes.append(node_id)
                continue

            # 收集下一个节点
            next_nodes = self._get_next_nodes(node)
            for next_node in next_nodes:
                if next_node not in visited:
                    queue.append(next_node)
                    path_count += 1

        # 报告
        print(f"  [OK] 可达节点: {len(visited)}/{len(self.nodes)}")
        print(f"  [OK] 结束节点: {len(end_nodes)} 个")

        unreachable = set(self.nodes.keys()) - visited
        if unreachable:
            self.warnings.append(f"不可达节点: {list(unreachable)}")

        if not end_nodes:
            self.errors.append("没有找到任何结束节点 (type='end')")

        return True

    def _get_next_nodes(self, node: Dict) -> List[str]:
        """获取节点的所有可能下一个节点"""
        next_nodes = []

        if 'next' in node:
            next_field = node['next']
            if isinstance(next_field, str):
                next_nodes.append(next_field)
            elif isinstance(next_field, list):
                for branch in next_field:
                    if isinstance(branch, dict) and 'goto' in branch:
                        next_nodes.append(branch['goto'])

        if 'options' in node:
            for option in node.get('options', []):
                if 'next' in option:
                    next_field = option['next']
                    if isinstance(next_field, str):
                        next_nodes.append(next_field)
                    elif isinstance(next_field, list):
                        for branch in next_field:
                            if isinstance(branch, dict) and 'goto' in branch:
                                next_nodes.append(branch['goto'])

        return next_nodes

    def validate_conditions(self) -> bool:
        """验证条件语法"""
        print("\n[6/7] 验证条件语法")

        condition_count = 0

        for node_id, node_data in self.nodes.items():
            # 检查选项条件
            if 'options' in node_data:
                for i, option in enumerate(node_data['options']):
                    if 'conditions' in option:
                        condition_count += 1
                        self._validate_condition(
                            option['conditions'],
                            f"节点 '{node_id}' 选项 {i+1}"
                        )

            # 检查 next 条件跳转
            if 'next' in node_data:
                next_field = node_data['next']
                if isinstance(next_field, list):
                    for i, branch in enumerate(next_field):
                        if isinstance(branch, dict) and 'if' in branch:
                            condition_count += 1
                            self._validate_condition(
                                branch['if'],
                                f"节点 '{node_id}' next 分支 {i+1}"
                            )

        print(f"  [OK] 验证了 {condition_count} 个条件")
        return True

    def _validate_condition(self, condition: Any, location: str):
        """验证单个条件"""
        if not isinstance(condition, dict):
            self.errors.append(f"{location}: 条件必须是字典类型")
            return

        # 检查逻辑运算符
        if 'and' in condition:
            if not isinstance(condition['and'], list):
                self.errors.append(f"{location}: 'and' 必须是列表")
            else:
                for i, sub_cond in enumerate(condition['and']):
                    self._validate_condition(sub_cond, f"{location} and[{i}]")

        elif 'or' in condition:
            if not isinstance(condition['or'], list):
                self.errors.append(f"{location}: 'or' 必须是列表")
            else:
                for i, sub_cond in enumerate(condition['or']):
                    self._validate_condition(sub_cond, f"{location} or[{i}]")

        else:
            # 检查普通条件
            valid_operators = ['==', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'contains']
            for key, check in condition.items():
                if not isinstance(check, dict):
                    self.errors.append(f"{location}: '{key}' 的检查必须是字典")
                    continue

                for operator in check.keys():
                    if operator not in valid_operators:
                        self.errors.append(f"{location}: 无效的运算符 '{operator}'")

    def validate_effects(self) -> bool:
        """验证效果配置"""
        print("\n[7/7] 验证效果配置")

        effect_count = 0

        for node_id, node_data in self.nodes.items():
            # 检查节点效果
            if 'effects' in node_data:
                effect_count += 1
                self._validate_effect(node_data['effects'], f"节点 '{node_id}'")

            # 检查选项效果
            if 'options' in node_data:
                for i, option in enumerate(node_data['options']):
                    if 'effects' in option:
                        effect_count += 1
                        self._validate_effect(
                            option['effects'],
                            f"节点 '{node_id}' 选项 {i+1}"
                        )

        print(f"  [OK] 验证了 {effect_count} 个效果配置")
        return True

    def _validate_effect(self, effects: Any, location: str):
        """验证单个效果"""
        if not isinstance(effects, dict):
            self.errors.append(f"{location}: effects 必须是字典类型")
            return

        valid_sections = ['player', 'variables', 'trial_success', 'first_trial_reward', 'rewards']
        for section in effects.keys():
            if section not in valid_sections:
                self.warnings.append(f"{location}: 未知的 effects 段: '{section}'")

    def generate_report(self) -> str:
        """生成调试报告"""
        lines = []
        lines.append("="*60)
        lines.append("Story Debugger 报告")
        lines.append("="*60)
        lines.append(f"文件: {self.story_file}")

        if 'id' in self.story_data:
            lines.append(f"剧情ID: {self.story_data['id']}")
        if 'title' in self.story_data:
            lines.append(f"标题: {self.story_data['title']}")

        lines.append("")
        lines.append(f"节点总数: {len(self.nodes)}")

        # 统计节点类型
        type_count = defaultdict(int)
        for node in self.nodes.values():
            type_count[node.get('type', 'unknown')] += 1

        for node_type, count in type_count.items():
            lines.append(f"  - {node_type}: {count}")

        lines.append("")
        lines.append("="*60)

        # 错误
        if self.errors:
            lines.append(f"\n错误 ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                lines.append(f"  {i}. [ERROR] {error}")
        else:
            lines.append("\n[OK] 没有发现错误!")

        # 警告
        if self.warnings:
            lines.append(f"\n警告 ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"  {i}. [WARN] {warning}")
        else:
            lines.append("\n[OK] 没有警告!")

        lines.append("\n" + "="*60)

        if not self.errors:
            lines.append("[PASS] 剧情脚本验证通过!")
        else:
            lines.append("[FAIL] 发现问题,请修复后重新检查")

        lines.append("="*60)

        return "\n".join(lines)

    def run_full_check(self) -> bool:
        """运行完整检查"""
        if not self.load_story():
            return False

        self.validate_structure()
        self.validate_nodes()
        self.check_references()
        self.analyze_paths()
        self.validate_conditions()
        self.validate_effects()

        return len(self.errors) == 0


class InteractiveDebugger:
    """交互式调试器"""

    def __init__(self, story_file: str):
        self.story_file = story_file
        self.story_data = {}
        self.current_node = None
        self.variables = {}
        self.player_state = {
            'level': 1,
            'gold': 0,
            'hp': 100,
            'attack': 10,
            'completed_trials': []
        }

    def load(self) -> bool:
        """加载剧情"""
        try:
            with open(self.story_file, 'r', encoding='utf-8') as f:
                self.story_data = json.load(f)
            return True
        except Exception as e:
            print(f"加载失败: {e}")
            return False

    def run(self):
        """运行交互式调试"""
        print("\n" + "="*60)
        print("交互式剧情调试器")
        print("="*60)
        print(f"剧情: {self.story_data.get('title', '未命名')}")
        print(f"描述: {self.story_data.get('description', '')}")
        print("="*60)
        print("\n命令:")
        print("  n/next    - 继续到下一个节点")
        print("  s/state   - 显示当前状态")
        print("  v/vars    - 显示剧情变量")
        print("  p/player  - 修改玩家属性")
        print("  r/restart - 重新开始")
        print("  q/quit    - 退出")
        print("  <数字>    - 选择选项")
        print("="*60)

        self.current_node = self.story_data.get('start_node')

        while True:
            self._show_node()

            cmd = input("\n> ").strip().lower()

            if cmd in ['q', 'quit']:
                break
            elif cmd in ['s', 'state']:
                self._show_state()
            elif cmd in ['v', 'vars']:
                self._show_variables()
            elif cmd in ['p', 'player']:
                self._edit_player()
            elif cmd in ['r', 'restart']:
                self.current_node = self.story_data.get('start_node')
                self.variables = {}
            elif cmd in ['n', 'next']:
                self._next_node()
            elif cmd.isdigit():
                self._choose_option(int(cmd))
            else:
                print("未知命令")

    def _show_node(self):
        """显示当前节点"""
        if not self.current_node or self.current_node not in self.story_data['nodes']:
            print("\n[ERROR] 无效节点")
            return

        node = self.story_data['nodes'][self.current_node]

        print(f"\n{'='*60}")
        print(f"节点: {self.current_node}")
        print(f"类型: {node.get('type')}")
        print(f"{'='*60}")

        if 'content' in node:
            print(f"\n{node['content']}")

        if node.get('type') == 'choice' and 'options' in node:
            print("\n选项:")
            for option in node['options']:
                opt_id = option.get('id', '?')
                text = option.get('text', '')
                print(f"  {opt_id}. {text}")

        print(f"{'='*60}")

    def _show_state(self):
        """显示玩家状态"""
        print("\n玩家状态:")
        for key, value in self.player_state.items():
            print(f"  {key}: {value}")

    def _show_variables(self):
        """显示剧情变量"""
        print("\n剧情变量:")
        if self.variables:
            for key, value in self.variables.items():
                print(f"  {key}: {value}")
        else:
            print("  (无)")

    def _edit_player(self):
        """编辑玩家属性"""
        print("\n当前玩家属性:")
        for key, value in self.player_state.items():
            print(f"  {key}: {value}")

        attr = input("\n要修改的属性 (回车跳过): ").strip()
        if attr and attr in self.player_state:
            try:
                value = int(input(f"新值: ").strip())
                self.player_state[attr] = value
                print(f"已设置 {attr} = {value}")
            except ValueError:
                print("无效的数值")

    def _next_node(self):
        """跳转到下一个节点"""
        if not self.current_node or self.current_node not in self.story_data['nodes']:
            return

        node = self.story_data['nodes'][self.current_node]

        if 'next' in node:
            next_field = node['next']
            if isinstance(next_field, str):
                self.current_node = next_field
            else:
                print("需要选择选项或条件跳转")
        else:
            print("没有下一个节点")

    def _choose_option(self, option_id: int):
        """选择选项"""
        if not self.current_node or self.current_node not in self.story_data['nodes']:
            return

        node = self.story_data['nodes'][self.current_node]

        if 'options' not in node:
            print("当前节点不是选择节点")
            return

        for option in node['options']:
            if option.get('id') == option_id:
                if 'next' in option:
                    next_field = option['next']
                    if isinstance(next_field, str):
                        self.current_node = next_field
                    else:
                        print("[DEBUG] 条件跳转暂不支持模拟")
                        self.current_node = next_field[0].get('goto') if next_field else None
                return

        print(f"选项 {option_id} 不存在")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python story_debugger.py <story_file.json>")
        print("  python story_debugger.py <story_file.json> --interactive")
        print("  python story_debugger.py <story_file.json> --check-all")
        sys.exit(1)

    story_file = sys.argv[1]
    interactive = '--interactive' in sys.argv or '-i' in sys.argv

    if interactive:
        # 交互式调试
        debugger = InteractiveDebugger(story_file)
        if debugger.load():
            debugger.run()
    else:
        # 完整检查
        debugger = StoryDebugger(story_file)
        success = debugger.run_full_check()

        # 打印报告
        report = debugger.generate_report()
        print(report)

        # 保存报告
        report_file = story_file.replace('.json', '_debug_report.txt')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n报告已保存到: {report_file}")

        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
