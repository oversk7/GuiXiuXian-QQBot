"""帮助文档一致性检查

扫描所有 on_command 注册的命令名（含别名），检查是否在
player/help.py 或 data/knowledge/*.yaml 中被提及。

- 管理员命令（同语句带 SUPERUSER）默认豁免。
- 历史欠账记录在 scripts/help_baseline.txt 中，不阻塞 CI；
  只有「新增且未写帮助」的命令会让检查失败。
- 已补齐文档的基线条目会被提示移除（不失败）。

用法：
  python scripts/check_help_consistency.py            # 检查（CI 用）
  python scripts/check_help_consistency.py --update-baseline   # 重新生成基线
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / "plugins" / "xiuxian_game"
BASELINE = Path(__file__).parent / "help_baseline.txt"

ON_COMMAND = re.compile(r'on_command\(\s*["\']([^"\']+)["\']([^)]*)\)', re.DOTALL)
ALIAS = re.compile(r'["\']([^"\']+)["\']')


def collect_commands():
    """返回 {命令名: 注册文件} ，跳过 SUPERUSER 命令。"""
    commands = {}
    for f in sorted(PLUGIN.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        for m in ON_COMMAND.finditer(text):
            name, blob = m.group(1), m.group(2)
            if "SUPERUSER" in blob:
                continue
            rel = str(f.relative_to(ROOT))
            commands.setdefault(name, rel)
            am = re.search(r"aliases\s*=\s*\{([^}]*)\}", blob)
            if am:
                for alias in ALIAS.findall(am.group(1)):
                    commands.setdefault(alias, rel)
    return commands


def build_corpus():
    parts = [(PLUGIN / "player" / "help.py").read_text(encoding="utf-8")]
    for f in sorted((PLUGIN / "data" / "knowledge").glob("*.yaml")):
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def main():
    update = "--update-baseline" in sys.argv
    commands = collect_commands()
    corpus = build_corpus()

    undocumented = sorted(name for name in commands if name not in corpus)

    if update:
        BASELINE.write_text(
            "# 帮助文档历史欠账（不阻塞 CI；新命令必须写帮助后才能通过检查）\n"
            + "\n".join(undocumented) + "\n",
            encoding="utf-8",
        )
        print(f"基线已更新：{len(undocumented)} 条欠账 → {BASELINE}")
        return 0

    baseline = set()
    if BASELINE.exists():
        baseline = {
            ln.strip() for ln in BASELINE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")
        }

    new_missing = [n for n in undocumented if n not in baseline]
    resolved = sorted(baseline - set(undocumented))

    print(f"命令总数（含别名，不含管理员命令）: {len(commands)}")
    print(f"未写帮助: {len(undocumented)}（基线欠账 {len(undocumented) - len(new_missing)}）")
    if resolved:
        print(f"\n以下 {len(resolved)} 条基线欠账已补齐文档，可从 help_baseline.txt 移除:")
        for n in resolved[:20]:
            print(f"  - {n}")
    if new_missing:
        print(f"\n❌ 以下 {len(new_missing)} 个命令缺少帮助文档（player/help.py 或 data/knowledge/*.yaml）:")
        for n in new_missing:
            print(f"  - {n}  (注册于 {commands[n]})")
        return 1
    print("✅ 无新增未写帮助的命令")
    return 0


if __name__ == "__main__":
    sys.exit(main())
