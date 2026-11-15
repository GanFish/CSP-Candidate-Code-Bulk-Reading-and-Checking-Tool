import argparse
import json
import queue
import re
import sys
import threading
from collections import Counter
from difflib import get_close_matches
from pathlib import Path

from core import (
    read_examinee, read_problem, read_all_examinees, open_target,
    analyze_code, load_rules, validate_rules,
)


# ============================================================
# 1. 路径处理
# ============================================================
_INVISIBLE = re.compile(r"[\u00A0\u200B-\u200F\uFEFF\r\n\t]")

def _clean(raw: str) -> str:
    s = raw.replace("\ufeff", "")
    s = _INVISIBLE.sub("", s)
    return s.strip().strip('"').strip("'").strip()

def _to_dir(raw: str) -> Path | None:
    s = _clean(raw)
    if not s:
        return None
    p = Path(s).expanduser().resolve()
    if not p.exists():
        print(f"[错误] 路径不存在：{p!r}")
        return None
    if not p.is_dir():
        print(f"[错误] 不是文件夹：{p}")
        return None
    return p


# ============================================================
# 2. 题名：自动检测 + 归一化
# ============================================================
def detect_standard_problems(all_codes, threshold=0.2):
    freq = Counter()
    for ps in all_codes.values():
        for p in ps.keys():
            freq[p.lower().strip()] += 1
    total = len(all_codes)
    if total == 0:
        return []
    return sorted(
        (name for name, n in freq.items() if n >= total * threshold),
        key=lambda name: -freq[name],
    )

def normalize(name: str, standard: list[str]) -> str:
    n = name.lower().strip()
    if n in {s.lower() for s in standard}:
        return n
    hit = get_close_matches(n, standard, n=1, cutoff=0.75)
    return hit[0].lower() if hit else n


# ============================================================
# 3. 汇总报告
# ============================================================
def report(all_codes, standard=None, preview=80):
    if not standard:
        standard = detect_standard_problems(all_codes)
        if standard:
            print(f"[信息] 自动识别标准题名（{len(standard)} 个）：{standard}")
        else:
            print("[警告] 无法自动识别题名，请用 --problems 手动指定")
            return None, None
    else:
        print(f"[信息] 使用手动指定题名：{standard}")

    full_set = {s.lower() for s in standard}
    norm = {sid: {normalize(p, standard): v for p, v in ps.items()}
            for sid, ps in all_codes.items()}
    complete = [sid for sid, ps in norm.items() if full_set <= set(ps)]
    missing  = {sid: sorted(full_set - set(ps))
                for sid, ps in norm.items() if full_set - set(ps)}

    print(f"\n{'=' * 64}")
    print(f"[统计] 总考生 {len(norm)} 人")
    if norm:
        print(f"       全部{len(full_set)}题齐全 {len(complete):>4} 人 "
              f"({len(complete) / len(norm):.1%})")
        print(f"       有缺题         {len(missing):>4} 人 "
              f"({len(missing) / len(norm):.1%})")

    miss_cnt = Counter(m for probs in missing.values() for m in probs)
    print(f"\n[各题缺交人数]")
    for prob in standard:
        n = miss_cnt.get(prob.lower(), 0)
        print(f"  {prob:<10} 缺 {n:>4} 人  (交 {len(norm) - n:>4})")

    k_cnt = Counter(len(v) for v in missing.values())
    print(f"\n[缺题数量分布]")
    for k in sorted(k_cnt):
        print(f"  缺 {k} 题: {k_cnt[k]:>4} 人")

    typo = [(sid, p, normalize(p, standard))
            for sid, ps in all_codes.items()
            for p in ps if p.lower() != normalize(p, standard)]
    if typo:
        print(f"\n[typo 修正] {len(typo)} 处：")
        for sid, old, new in typo[:10]:
            print(f"  {sid}: '{old}' → '{new}'")
        if len(typo) > 10:
            print(f"  ... 共 {len(typo)} 处")

    if preview > 0:
        print(f"\n[前 20 名考生预览]")
        for sid in sorted(norm.keys())[:20]:
            print(f"  {sid:<16} → {sorted(norm[sid].keys())}")

    return norm, missing


# ============================================================
# 4. 内容检查
# ============================================================
def run_check(all_codes, rules, *, ignore_case=False, strip_comments=False,
              verbose=False, export=None, stop_event=None):
    ok, err = validate_rules(rules, ignore_case)
    if not ok:
        print(f"[错误] 规则有误：{err}")
        return

    rule_counter = Counter()
    student_hit  = set()
    per_hit = {}
    interrupted = False

    for sid, problems in all_codes.items():
        if stop_event is not None and stop_event.is_set():
            print("\n[中断] 用户请求停止检查")
            interrupted = True
            break

        for prob, (path, code) in problems.items():
            if stop_event is not None and stop_event.is_set():
                print("\n[中断] 用户请求停止检查")
                interrupted = True
                break

            res = analyze_code(code, rules,
                               ignore_case=ignore_case,
                               strip_comments=strip_comments)
            if not res["matched"]:
                continue
            student_hit.add(sid)
            for cat, kw_lines in res["details"].items():
                if not kw_lines:
                    continue
                for kw, lines in kw_lines.items():
                    rule_counter[kw] += 1
                    per_hit.setdefault(sid, {}) \
                           .setdefault(cat, {}) \
                           .setdefault(kw, []) \
                           .append({"problem": prob,
                                    "path": str(path),
                                    "lines": lines})

        if interrupted:
            break

    print(f"\n{'=' * 64}")
    print(f"[检查] 共检查 {len(all_codes)} 名考生"
          + ("（已中断）" if interrupted else ""))
    if all_codes:
        print(f"       命中考生 {len(student_hit)} 人 "
              f"({len(student_hit) / len(all_codes):.1%})")

    if not rule_counter:
        print("\n[结果] 没有任何规则命中 ✅")
        if export:
            _write_export(export, rules, ignore_case, strip_comments,
                          all_codes, student_hit, rule_counter, per_hit)
        return

    print(f"\n[规则命中统计]")
    for kw, n in rule_counter.most_common():
        print(f"  {kw:<28} 命中 {n:>4} 次")

    if isinstance(rules, dict):
        print(f"\n[按分类]")
        for cat in rules:
            n = sum(1 for d in per_hit.values() if cat in d)
            if n:
                print(f"  {cat:<16} 命中考生 {n:>4} 人")

    if verbose:
        print(f"\n[命中明细]（前 30 名考生）")
        for sid in sorted(per_hit.keys())[:30]:
            print(f"\n  {sid}")
            for cat, kw_d in per_hit[sid].items():
                for kw, items in kw_d.items():
                    for it in items:
                        print(f"    [{cat}] {kw}  →  "
                              f"{it['problem']}  行 {it['lines'][:10]}"
                              f"{' ...' if len(it['lines']) > 10 else ''}")

    if export:
        _write_export(export, rules, ignore_case, strip_comments,
                      all_codes, student_hit, rule_counter, per_hit)


def _write_export(export, rules, ignore_case, strip_comments,
                  all_codes, student_hit, rule_counter, per_hit):
    out = {
        "rules": rules,
        "ignore_case": ignore_case,
        "strip_comments": strip_comments,
        "total_students": len(all_codes),
        "hit_students": len(student_hit),
        "rule_counts": dict(rule_counter),
        "details": {
            sid: {
                cat: {
                    kw: [
                        {"problem": it["problem"], "path": it["path"],
                         "lines": it["lines"]}
                        for it in items
                    ]
                    for kw, items in kw_d.items()
                }
                for cat, kw_d in cats.items()
            }
            for sid, cats in per_hit.items()
        },
    }
    Path(export).write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[导出] 已保存到 {Path(export).resolve()}")


# ============================================================
# 5. 可中断的批量读取
# ============================================================
def _read_all_with_stop(csp_dir, stop_event,
                        filename=None, min_score=None, verbose=False):
    csp_dir = Path(csp_dir)
    if not csp_dir.is_dir():
        return {}

    out = {}
    total = 0
    for s in sorted(csp_dir.iterdir()):
        if stop_event is not None and stop_event.is_set():
            print(f"\n[中断] 已读取 {len(out)} 名考生后停止")
            break
        if (not s.is_dir()
                or s.name.startswith((".", "_"))
                or s.name == "__MACOSX"):
            continue
        total += 1
        if total % 200 == 0:
            print(f"[进度] 已读取 {total} 名考生...")
        out[s.name] = read_examinee(s, filename=filename,
                                    min_score=min_score, verbose=False)
    return out


# ============================================================
# 6. 核心执行逻辑
# ============================================================
def execute(args, stop_event=None):
    standard = None
    if args.problems:
        standard = [p.strip().lower() for p in args.problems.split(",") if p.strip()]
        if not standard:
            print("[错误] --problems 参数为空")
            return

    root = _to_dir(args.root)
    if root is None:
        return
    print(f"[信息] 比赛根目录：{root}\n")

    # ---------- 检查模式 ----------
    if args.check:
        if not args.rules and not args.rules_file:
            print("[错误] --check 模式需要 --rules 或 --rules-file")
            return

        try:
            if isinstance(args.rules, (list, dict)):
                rules = args.rules
            else:
                rules = load_rules(args.rules, args.rules_file)
        except (FileNotFoundError, ValueError) as e:
            print(f"[错误] 规则加载失败：{e}")
            return
        if not rules:
            print("[错误] 规则为空")
            return

        ok, err = validate_rules(rules, args.ignore_case)
        if not ok:
            print(f"[错误] 规则有误：{err}")
            return

        if args.student:
            codes = read_examinee(root / args.student,
                                  filename=args.filename,
                                  min_score=args.min_score,
                                  verbose=args.verbose)
            if not codes:
                print(f"[信息] 考生 {args.student} 下没有 .cpp")
                return
            all_codes = {args.student: codes}
        else:
            all_codes = _read_all_with_stop(
                root, stop_event,
                filename=args.filename,
                min_score=args.min_score,
                verbose=args.verbose,
            )
            if not all_codes:
                print(f"[信息] {root} 下没有找到任何考生文件夹")
                return
        print(f"[信息] 已读取 {len(all_codes)} 名考生的代码")
        run_check(all_codes, rules,
                  ignore_case=args.ignore_case,
                  strip_comments=args.strip_comments,
                  verbose=args.verbose,
                  export=args.export,
                  stop_event=stop_event)
        return

    # ---------- 读取模式：单考生 + 单题 ----------
    if args.student and args.problem:
        target = root / args.student / args.problem
        r = read_problem(target, filename=args.filename,
                         min_score=args.min_score, verbose=True)
        if r is None:
            print(f"[跳过] {target} 无可读 .cpp")
            return
        path, code = r
        print(f"\n[{args.student}/{args.problem}]  {path.name}  "
              f"{len(code)} 字符")
        print("-" * 64)
        print(code[:500])
        return

    # ---------- 读取模式：单考生所有题 ----------
    if args.student:
        codes = read_examinee(root / args.student,
                              filename=args.filename,
                              min_score=args.min_score,
                              verbose=args.verbose)
        if not codes:
            print(f"[信息] 考生 {args.student} 下没有找到任何 .cpp")
            return
        if standard:
            codes = {normalize(p, standard): v for p, v in codes.items()}
        print(f"[信息] 考生 {args.student} 共 {len(codes)} 道题\n")
        for problem, (path, code) in codes.items():
            print(f"[{problem:<12}]  {path}")
            if args.show_code > 0:
                snippet = code[:args.show_code].replace("\n", " ")
                print(f"  {snippet} ...\n")
        return

    # ---------- 读取模式：全量 ----------
    all_codes = _read_all_with_stop(
        root, stop_event,
        filename=args.filename,
        min_score=args.min_score,
        verbose=args.verbose,
    )
    if not all_codes:
        print(f"[信息] {root} 下没有找到任何考生文件夹")
        return
    print(f"[完成] 共处理 {len(all_codes)} 名考生")
    report(all_codes, standard=standard, preview=args.show_code)


# ============================================================
# 7. 命令行参数
# ============================================================
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="CSP-J/S 考生代码批量读取与检查工具（CLI + GUI）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "模式:\n"
            "  不传任何参数        → 启动 Tkinter GUI\n"
            "  --gui               → 强制启动 GUI\n"
            "  传路径              → 进入 CLI 模式\n"
            "\n"
            "CLI 示例:\n"
            '  python main.py "D:/CSP/CSP-J"\n'
            '  python main.py "D:/CSP/CSP-S" --problems lockout,slime,arena,xxx\n'
            '  python main.py "D:/CSP/CSP-J" --student HE-J00001 --problem travel\n'
            '  python main.py "D:/CSP/CSP-J" --check --rules "freopen,system"\n'
            '  python main.py "D:/CSP/CSP-J" --check --rules-file rules.json -v\n'
        ),
    )
    ap.add_argument("root", nargs="?", default=None,
                    help="比赛根目录；不给且未 --gui 则启动 GUI")
    ap.add_argument("--gui", action="store_true",
                    help="强制启动 GUI 模式")
    ap.add_argument("--student", help="只看某个考生，如 HE-J00001")
    ap.add_argument("--problem", help="只看某道题，如 travel")
    ap.add_argument("--filename", help="优先匹配的 .cpp 文件名，如 travel.cpp")
    ap.add_argument("--min-score", type=float, default=None,
                    help="文件名相似度阈值（0~1），低于该值视为无匹配")
    ap.add_argument("--problems", metavar="A,B,C,D",
                    help="手动指定题名，逗号分隔（不传则自动检测）")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="输出详细信息")
    ap.add_argument("--show-code", type=int, default=80, metavar="N",
                    help="单题预览字符数（默认 80，0 表示不显示）")
    ap.add_argument("--check", action="store_true",
                    help="进入代码内容检查模式")
    ap.add_argument("--rules", metavar="KW1,KW2,...",
                    help="检查规则（逗号分隔；支持 re: 前缀开正则；支持 \\, 转义逗号）")
    ap.add_argument("--rules-file", metavar="FILE",
                    help="从文件加载规则（.json 或 .txt）")
    ap.add_argument("--ignore-case", action="store_true",
                    help="检查时忽略大小写")
    ap.add_argument("--strip-comments", action="store_true",
                    help="检查前剥离注释（默认关闭，显式开启才生效）")
    ap.add_argument("--export", metavar="OUT.json",
                    help="检查模式下导出结果到 JSON")
    return ap.parse_args(argv)


# ============================================================
# 8. GUI
# ============================================================
class _QueueWriter:
    def __init__(self, q):
        self.q = q
    def write(self, s):
        if s:
            self.q.put(s)
    def flush(self):
        pass


def _quote(s: str) -> str:
    """为 PowerShell 命令行转义参数。"""
    if not s:
        return "''"
    if all(c.isalnum() or c in "._-/\\:" for c in s):
        return s
    return "'" + s.replace("'", "''") + "'"


# ============================================================
# 帮助文本（详细解释每一个控件）
# ============================================================
HELP_TEXT = """\
【CSP 考生代码批量读取与检查工具 —— 使用说明】
========================================================================

一、数据位置
------------------------------------------------------------------------
比赛根目录
    必填。指向 CSP 数据的根目录，其下应是一个个考生文件夹
    （如 HE-J00001/、HE-J00002/…）。
    例：D:/CSP/End/CSP-J
    支持：
      · 绝对路径（推荐）
      · 相对路径（相对 main.py 的位置）
      · 含 ~ 的路径（自动展开为家目录）
      · 拖拽文件夹到输入框（自动去掉首尾引号）
      · 粘贴路径带空格也可以

浏览...
    打开文件夹选择对话框，用鼠标选路径。

打开
    用系统资源管理器打开当前填写的路径。方便核对数据。

考生(可选)
    只处理这一名考生，例：HE-J00001。
    留空 = 处理根目录下所有考生。
    提示：填了考生后，读取模式会列出他的所有题目及预览。

题目(可选)
    只处理这一道题，例：travel。
    必须配合"考生"字段使用（单独填无效）。
    填了之后会直接打印该 .cpp 的前 500 字符，用于人工审阅。

题名(可选)
    手动指定"标准题名"，逗号分隔，例：lockout,slime,arena,xxx。
    留空 = 程序从数据中自动检测（推荐，J 组和 S 组都适用）。
    仅当自动检测出错（如识出"新建文件夹"）时才需要手动填。

.cpp文件名
    优先匹配的 .cpp 文件名，例：travel.cpp。
    留空 = 每题自动挑"最像题目名"的那个 .cpp。
    填了之后按相似度打分挑选，可处理 .cpp 命名不规范的考生。

最小相似度
    与 .cpp文件名配合使用，范围 0~1。
    留空 = 总是选"最像"的一个（不会失败）。
    填了数字 = 相似度低于它视为无匹配，该考生该题跳过。
    例：0.5 表示至少一半相似度才算匹配。

预览字符数
    单题预览显示多少字符，默认 80。
    填 0 = 只显示文件路径，不预览内容。
    填 500 = 显示前 500 个字符，用于人工核对。


二、模式
------------------------------------------------------------------------
读取统计（缺题/完整性）
    不分析代码内容，只统计：
      · 每个考生交了几题
      · 每题有多少人缺交
      · 每人缺几题（区分"缺 1 题"和"完全弃考"）
      · 自动修正目录名 typo（如 travle → travel）
      · 自动检测标准题名（J 组和 S 组都适用）

内容检查（关键字/正则）
    逐行扫描代码，统计命中了哪些关键字或正则。
    详细规则见下方"检查规则与选项"。

详细日志(-v)
    勾选后输出会"啰嗦"：
      · 读取模式：显示每个被跳过的目录、套娃考生的修正记录
      · 检查模式：显示每个考生具体在哪一题哪一行命中
    默认不勾选，避免上千行日志刷屏。


三、执行按钮
------------------------------------------------------------------------
▶ 开始执行
    按当前配置运行任务。
    快捷键：Ctrl+R

■ 停止
    软中断。发出停止信号后，当前正在读取的考生读完即停。
    最坏延迟 = 读取 1 名考生的时间（通常 <100ms）。
    已读到的数据会照常输出统计。

🗑 清空输出
    清空下方的输出区，不影响任何数据。
    快捷键：Esc

📋 显示等价命令
    把当前 GUI 配置序列化为一条 python main.py ... 的命令，
    显示在输出区。
    用途：
      · 验证 GUI 与 CLI 行为一致
      · 把 GUI 配置直接复制成脚本 / 定时任务
      · 复现问题时提供"可重复命令"


四、检查规则与选项（仅"内容检查"模式显示）
------------------------------------------------------------------------
规则文本框
    支持四种写法：
      1) 一行一条关键字：
           freopen
           system
           while(1)
      2) 一行里逗号分隔：
           freopen,system,while(1)
      3) 以 { 开头的 JSON 字典（可分类）：
           {
             "危险函数": ["system", "popen"],
             "文件操作": ["freopen", "fopen"]
           }
      4) re: 前缀走正则：
           re:while\\s*\\(\\s*1\\s*\\)
           re:\\bgoto\\b
    注意：
      · TXT 文件里注释用 "# "（井号+空格）或 "##"，
        这样 #include / #define / #pragma 不会被当成注释吃掉
      · 命令行 --rules 支持 \\, 转义逗号

加载规则文件...
    从 .json / .txt 读取内容到文本框。
    读入后仍可继续编辑。

清空规则
    清空文本框。

示例 JSON
    一键填入一组示范规则（危险函数 / 文件操作 / 死循环 / 禁用头文件 / 可疑跳转），
    可直接作为模板修改。

忽略大小写
    默认关闭。
    C++ 是大小写敏感的（System ≠ system），一般不需要开。
    只有在"想抓任意大小写形式的关键字"时才勾选。

剥离注释
    默认关闭（本次更新）。
    勾选后：先剥离 // 行注释和 /* */ 块注释，再检查关键字。
    用途：避免"注释里出现关键字"造成的误报。
    副作用：如果规则本身就是要查注释（如 "// TODO"），别开这个。

导出到
    检查完成后把详细结果写成 JSON。
    包含：规则命中统计、每个考生的命中题目和行号。
    留空 = 不导出。
    点右侧 "..." 打开保存对话框。


五、输出区
------------------------------------------------------------------------
    深色背景，等宽字体，实时显示 print 输出。
    可拖选、Ctrl+A 全选、Ctrl+C 复制。
    点"清空输出"或按 Esc 清空。
    状态栏显示当前状态（就绪 / 运行中 / 完成 / 已停止）。


六、快捷键
------------------------------------------------------------------------
    F1              打开本帮助
    Ctrl+R          开始执行
    Esc             清空输出（在帮助/关于窗口里则是关闭窗口）
    Ctrl+A / Ctrl+C 输出区全选/复制


七、命令行参数对照
------------------------------------------------------------------------
    完整参数列表见：  python main.py --help

    主要参数：
      root                    比赛根目录
      --gui                   强制启动 GUI
      --student NAME          只看某个考生
      --problem NAME          只看某道题（需配合 --student）
      --problems A,B,C,D      手动指定题名
      --filename FILE         优先匹配的 .cpp 文件名
      --min-score FLOAT       相似度阈值（0~1）
      --show-code N           单题预览字符数（默认 80）
      -v / --verbose          详细日志
      --check                 进入检查模式
      --rules "a,b,c"         检查规则（逗号分隔）
      --rules-file FILE       从文件加载规则
      --ignore-case           忽略大小写
      --strip-comments        剥离注释（默认关闭）
      --export OUT.json       导出检查结果

    常用示例：
      python main.py "D:/CSP/CSP-J"
      python main.py "D:/CSP/CSP-S" --problems lockout,slime,arena,xxx
      python main.py "D:/CSP/CSP-J" --check --rules "freopen,system"
      python main.py "D:/CSP/CSP-J" --check --rules-file rules.json -v
"""

ABOUT_TEXT = """\
CSP 考生代码批量读取与检查工具
版本 1.0
========================================================================
注：大量使用了大肥鱼（DeepSeek）来编写！！！
功能：
  · 批量读取 CSP-J / CSP-S 考生的源代码
  · 自动检测编码（UTF-8 / GBK / GB18030 / UTF-8-BOM）
  · 按目录结构（考生 / 题目 / .cpp）定位文件
  · 自动检测题名，CSP-J 与 CSP-S 通用
  · 统计缺题 / 完整性
  · 自动修正目录名 typo
  · 处理"套娃"考生目录（HE-J00424/HE-J00424/...）
  · 内容检查（关键字 / 正则 / 分类）
  · 剥离注释 / 忽略大小写 / 导出 JSON
  · 支持命令行和 Tkinter GUI

依赖：
  · Python 3.9+
  · charset-normalizer（自动检测编码）

目录结构约定：
  CSP-J/
    HE-J00001/
      travel/travel.cpp
      and/and.cpp
      ...
    HE-J00002/...

作者：GanFish
反馈邮箱：sxy12333hh@qq.com
"""


def launch_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox, scrolledtext
    except ImportError:
        print("[错误] 当前 Python 未安装 tkinter（Windows 官方版自带）")
        return

    output_queue: queue.Queue = queue.Queue()

    app = tk.Tk()
    app.title("CSP 考生代码批量读取与检查工具")
    app.minsize(900, 700)
    try:
        app.option_add("*Font", ("Microsoft YaHei UI", 10))
    except Exception:
        pass

    w, h = 1040, 920
    sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
    app.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")

    # ---------- 变量 ----------
    var_root           = tk.StringVar()
    var_student        = tk.StringVar()
    var_problem        = tk.StringVar()
    var_problems       = tk.StringVar()
    var_filename       = tk.StringVar()
    var_min_score      = tk.StringVar()
    var_show_code      = tk.StringVar(value="80")
    var_mode           = tk.StringVar(value="read")
    var_ignore_case    = tk.BooleanVar(value=False)
    var_strip_comments = tk.BooleanVar(value=False)   # 默认关
    var_verbose        = tk.BooleanVar(value=False)
    var_export         = tk.StringVar()
    var_status         = tk.StringVar(value="就绪")

    state = {"running": False, "check_visible": False}
    stop_event = threading.Event()

    main = ttk.Frame(app, padding=10)
    main.pack(fill="both", expand=True)

    # ===== 数据位置 =====
    loc = ttk.LabelFrame(main, text="数据位置", padding=8)
    loc.pack(fill="x", pady=(0, 8))

    ttk.Label(loc, text="比赛根目录:").grid(row=0, column=0, sticky="w")
    ttk.Entry(loc, textvariable=var_root).grid(row=0, column=1, sticky="we", padx=4)
    ttk.Button(loc, text="浏览...", command=lambda: _pick_dir()).grid(row=0, column=2)
    ttk.Button(loc, text="打开", command=lambda: _open_dir()).grid(row=0, column=3, padx=(4, 0))
    loc.columnconfigure(1, weight=1)

    ttk.Label(loc, text="考生(可选):").grid(row=1, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(loc, textvariable=var_student).grid(row=1, column=1, sticky="we", padx=4, pady=(4, 0))
    ttk.Label(loc, text="题目(可选):").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
    ttk.Entry(loc, textvariable=var_problem, width=15).grid(row=1, column=3, sticky="we", padx=4, pady=(4, 0))

    ttk.Label(loc, text="题名(可选):").grid(row=2, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(loc, textvariable=var_problems).grid(row=2, column=1, sticky="we", padx=4, pady=(4, 0))
    ttk.Label(loc, text=".cpp文件名:").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(4, 0))
    ttk.Entry(loc, textvariable=var_filename, width=15).grid(row=2, column=3, sticky="we", padx=4, pady=(4, 0))

    ttk.Label(loc, text="最小相似度:").grid(row=3, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(loc, textvariable=var_min_score, width=8).grid(row=3, column=1, sticky="w", padx=4, pady=(4, 0))
    ttk.Label(loc, text="(留空=不限制，范围 0~1)", foreground="gray").grid(
        row=3, column=2, columnspan=2, sticky="w", pady=(4, 0))

    ttk.Label(loc, text="预览字符数:").grid(row=4, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(loc, textvariable=var_show_code, width=8).grid(
        row=4, column=1, sticky="w", padx=4, pady=(4, 0))
    ttk.Label(loc, text="(单题预览长度，0=不显示)", foreground="gray").grid(
        row=4, column=2, columnspan=2, sticky="w", pady=(4, 0))

    # ===== 模式 =====
    mode = ttk.LabelFrame(main, text="模式", padding=8)
    mode.pack(fill="x", pady=(0, 8))
    ttk.Radiobutton(mode, text="读取统计（缺题/完整性）", variable=var_mode,
                    value="read", command=lambda: _update_mode()).pack(side="left", padx=8)
    ttk.Radiobutton(mode, text="内容检查（关键字/正则）", variable=var_mode,
                    value="check", command=lambda: _update_mode()).pack(side="left", padx=8)
    ttk.Checkbutton(mode, text="详细日志(-v)", variable=var_verbose).pack(side="left", padx=(20, 0))

    # ===== 执行按钮 =====
    action = ttk.Frame(main)
    action.pack(fill="x", pady=(0, 8))
    btn_run = ttk.Button(action, text="▶  开始执行", command=lambda: _run())
    btn_run.pack(side="left")
    btn_stop = ttk.Button(action, text="■  停止", command=lambda: _stop(),
                          state="disabled")
    btn_stop.pack(side="left", padx=6)
    ttk.Button(action, text="🗑  清空输出",
               command=lambda: _clear_output()).pack(side="left")
    ttk.Button(action, text="📋  显示等价命令",
               command=lambda: _show_equiv_cmd()).pack(side="left", padx=6)
    ttk.Button(action, text="❓  帮助",
               command=lambda: _show_help()).pack(side="left", padx=(0, 6))
    progress = ttk.Progressbar(action, mode="indeterminate")
    progress.pack(side="left", fill="x", expand=True, padx=8)

    # ===== 检查区 =====
    check = ttk.LabelFrame(main, text="检查规则与选项", padding=8)

    ttk.Label(check,
              text="规则（一行一条 / 逗号分隔 / JSON 字典，支持 re: 前缀；"
                   "TXT 文件里注释用 '# ' 或 '##'）："
              ).pack(anchor="w")
    rules_container = ttk.Frame(check)
    rules_container.pack(fill="both", expand=True, pady=(4, 4))
    rules_text = scrolledtext.ScrolledText(
        rules_container, height=8, wrap="word", font=("Consolas", 9))
    rules_text.pack(fill="both", expand=True)
    rules_text.insert("1.0", "freopen\nsystem\nwhile(1)")

    btn_row = ttk.Frame(check)
    btn_row.pack(fill="x", pady=(4, 4))
    ttk.Button(btn_row, text="加载规则文件...",
               command=lambda: _load_rules()).pack(side="left", padx=(0, 4))
    ttk.Button(btn_row, text="清空规则",
               command=lambda: rules_text.delete("1.0", "end")).pack(side="left")
    ttk.Button(btn_row, text="示例 JSON",
               command=lambda: _fill_demo_rules()).pack(side="left", padx=4)

    opts = ttk.Frame(check)
    opts.pack(fill="x")
    ttk.Checkbutton(opts, text="忽略大小写",
                    variable=var_ignore_case).pack(side="left", padx=4)
    ttk.Checkbutton(opts, text="剥离注释",
                    variable=var_strip_comments).pack(side="left", padx=4)
    ttk.Label(opts, text="  导出到:").pack(side="left")
    ttk.Entry(opts, textvariable=var_export, width=25).pack(side="left", padx=4)
    ttk.Button(opts, text="...", command=lambda: _pick_export()).pack(side="left")

    # ===== 输出区 =====
    out_frame = ttk.LabelFrame(main, text="输出", padding=4)
    out_frame.pack(fill="both", expand=True)
    output_text = scrolledtext.ScrolledText(
        out_frame, wrap="word", state="disabled",
        bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
        font=("Consolas", 9),
    )
    output_text.pack(fill="both", expand=True)

    ttk.Label(app, textvariable=var_status, relief="sunken",
              anchor="w").pack(fill="x", side="bottom")

    # ============================================================
    # 菜单栏
    # ============================================================
    menubar = tk.Menu(app)

    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="选择数据目录...", command=lambda: _pick_dir())
    file_menu.add_command(label="打开数据目录", command=lambda: _open_dir())
    file_menu.add_separator()
    file_menu.add_command(label="退出", command=app.destroy)
    menubar.add_cascade(label="文件", menu=file_menu)

    help_menu = tk.Menu(menubar, tearoff=0)
    help_menu.add_command(label="使用说明", accelerator="F1",
                          command=lambda: _show_help())
    help_menu.add_command(label="关于", command=lambda: _show_about())
    menubar.add_cascade(label="帮助", menu=help_menu)

    app.configure(menu=menubar)

    # ============================================================
    # 回调
    # ============================================================
    def _append_output(s):
        output_text.configure(state="normal")
        output_text.insert("end", s)
        output_text.see("end")
        output_text.configure(state="disabled")

    def _pick_dir():
        d = filedialog.askdirectory(title="选择比赛根目录")
        if d:
            var_root.set(d)

    def _open_dir():
        d = var_root.get().strip()
        if not d:
            return
        try:
            import subprocess
            if sys.platform == "win32":
                import os
                os.startfile(d)   # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def _pick_export():
        f = filedialog.asksaveasfilename(
            title="导出结果", defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if f:
            var_export.set(f)

    def _load_rules():
        f = filedialog.askopenfilename(
            title="选择规则文件",
            filetypes=[
                ("规则文件", "*.json *.txt"),
                ("JSON", "*.json"),
                ("文本", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if not f:
            return
        try:
            text = Path(f).read_text(encoding="utf-8-sig")
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        rules_text.delete("1.0", "end")
        rules_text.insert("1.0", text)

    def _fill_demo_rules():
        demo = r'''{
  "危险函数": ["system", "popen", "exec", "fork", "gets"],
  "文件操作": ["freopen", "fopen", "ifstream", "ofstream"],
  "死循环":   ["while(1)", "while(true)", "for(;;)", "re:while\\s*\\(\\s*1\\s*\\)"],
  "禁用头文件": ["#include<bits/stdc++.h>", "#include<windows.h>"],
  "可疑跳转": ["re:\\bgoto\\b"]
}'''
        rules_text.delete("1.0", "end")
        rules_text.insert("1.0", demo)

    def _update_mode():
        if var_mode.get() == "check":
            if not state["check_visible"]:
                check.pack(fill="x", pady=(0, 8), before=action)
                state["check_visible"] = True
        else:
            if state["check_visible"]:
                check.pack_forget()
                state["check_visible"] = False

    def _clear_output():
        output_text.configure(state="normal")
        output_text.delete("1.0", "end")
        output_text.configure(state="disabled")

    def _parse_rules_gui():
        text = rules_text.get("1.0", "end").strip()
        if not text:
            return None
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"JSON 解析失败（第 {e.lineno} 行第 {e.colno} 列）：{e.msg}\n"
                    f"常见原因：反斜杠没双写（\\b → \\\\b）、引号没转义"
                )
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("##"):
                continue
            if len(s) >= 2 and s[0] == "#" and s[1] in (" ", "\t"):
                continue
            out.append(s)
        return out

    def _build_namespace():
        ns = argparse.Namespace()
        ns.root        = var_root.get().strip()
        ns.student     = var_student.get().strip() or None
        ns.problem     = var_problem.get().strip() or None
        ns.filename    = var_filename.get().strip() or None
        ns.problems    = var_problems.get().strip() or None
        ns.verbose     = var_verbose.get()
        ns.check       = var_mode.get() == "check"
        ns.ignore_case = var_ignore_case.get()
        ns.strip_comments = var_strip_comments.get()
        ns.export      = var_export.get().strip() or None
        ns.rules_file  = None
        ns.rules       = None

        sc = var_show_code.get().strip()
        try:
            ns.show_code = int(sc) if sc else 80
            if ns.show_code < 0:
                raise ValueError("不能为负")
        except ValueError:
            messagebox.showerror(
                "错误", f"预览字符数无效：{sc}（应为非负整数）")
            return None

        ms = var_min_score.get().strip()
        if ms:
            try:
                ns.min_score = float(ms)
            except ValueError:
                messagebox.showerror("错误", f"最小相似度无效：{ms}")
                return None
        else:
            ns.min_score = None

        if ns.check:
            try:
                ns.rules = _parse_rules_gui()
            except ValueError as e:
                messagebox.showerror("规则解析错误", str(e))
                return None
            if not ns.rules:
                messagebox.showerror("错误", "检查模式需要至少一条规则")
                return None

        return ns

    def _show_equiv_cmd():
        ns = _build_namespace()
        if ns is None:
            return

        parts = ["python main.py"]
        if ns.root:
            parts.append(_quote(ns.root))
        if ns.student:
            parts.append(f"--student {_quote(ns.student)}")
        if ns.problem:
            parts.append(f"--problem {_quote(ns.problem)}")
        if ns.filename:
            parts.append(f"--filename {_quote(ns.filename)}")
        if ns.problems:
            parts.append(f"--problems {_quote(ns.problems)}")
        if ns.min_score is not None:
            parts.append(f"--min-score {ns.min_score}")
        if ns.show_code != 80:
            parts.append(f"--show-code {ns.show_code}")
        if ns.verbose:
            parts.append("--verbose")
        if ns.check:
            parts.append("--check")
            if ns.ignore_case:
                parts.append("--ignore-case")
            if ns.strip_comments:
                parts.append("--strip-comments")
            if ns.export:
                parts.append(f"--export {_quote(ns.export)}")
            rules_src = rules_text.get("1.0", "end").strip()
            if rules_src:
                if "\n" in rules_src or len(rules_src) > 100:
                    parts.append("--rules-file rules.json  # ← 把当前规则另存为文件")
                else:
                    parts.append(f"--rules {_quote(rules_src)}")

        cmd = " ".join(parts)
        _append_output(
            f"\n{'=' * 60}\n"
            f"[等价命令行]\n"
            f"{cmd}\n"
            f"{'=' * 60}\n"
        )

    def _show_help():
        win = tk.Toplevel(app)
        win.title("使用说明")
        win.geometry("860x720")
        win.transient(app)
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)

        txt = scrolledtext.ScrolledText(
            frame, wrap="word",
            font=("Microsoft YaHei UI", 10), padx=8, pady=8)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right")

        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<F1>", lambda e: win.destroy())
        txt.focus_set()

    def _show_about():
        win = tk.Toplevel(app)
        win.title("关于")
        win.geometry("640x560")
        win.transient(app)
        frame = ttk.Frame(win, padding=8)
        frame.pack(fill="both", expand=True)

        txt = scrolledtext.ScrolledText(
            frame, wrap="word",
            font=("Microsoft YaHei UI", 10), padx=8, pady=8)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", ABOUT_TEXT)
        txt.configure(state="disabled")

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="关闭", command=win.destroy).pack(side="right")

        win.bind("<Escape>", lambda e: win.destroy())
        win.focus_set()

    def _run():
        if state["running"]:
            return

        ns = _build_namespace()
        if ns is None:
            return

        if not ns.root:
            messagebox.showerror("错误", "请先选择比赛根目录")
            return

        _clear_output()
        stop_event.clear()
        state["running"] = True
        btn_run.configure(state="disabled")
        btn_stop.configure(state="normal")
        progress.start(10)
        var_status.set("运行中...")

        def worker():
            orig_out, orig_err = sys.stdout, sys.stderr
            try:
                sys.stdout = _QueueWriter(output_queue)
                sys.stderr = sys.stdout
                execute(ns, stop_event=stop_event)
            except SystemExit:
                pass
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                sys.stdout = orig_out
                sys.stderr = orig_err
                app.after(0, _on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _stop():
        if not state["running"]:
            return
        stop_event.set()
        var_status.set("正在停止（等待当前考生读取完）...")
        btn_stop.configure(state="disabled")

    def _on_done():
        state["running"] = False
        btn_run.configure(state="normal")
        btn_stop.configure(state="disabled")
        progress.stop()
        var_status.set("已停止" if stop_event.is_set() else "完成")
        _drain_once()

    def _drain_once():
        try:
            while True:
                s = output_queue.get_nowait()
                output_text.configure(state="normal")
                output_text.insert("end", s)
                output_text.see("end")
                output_text.configure(state="disabled")
        except queue.Empty:
            pass

    def _periodic_drain():
        _drain_once()
        app.after(100, _periodic_drain)

    # 快捷键
    app.bind("<F1>", lambda e: _show_help())
    app.bind("<Control-r>", lambda e: _run())
    app.bind("<Escape>", lambda e: _clear_output())

    _update_mode()
    _periodic_drain()
    app.mainloop()


# ============================================================
# 9. 入口
# ============================================================
def main():
    args = parse_args()
    if args.gui or args.root is None:
        launch_gui()
        return
    execute(args)


if __name__ == "__main__":
    main()