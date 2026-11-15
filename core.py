from pathlib import Path
from difflib import SequenceMatcher
import json
import re

from charset_normalizer import from_path   # pip install charset-normalizer


# ============================================================
# 1. 自动编码读取单个文件
# ============================================================
def read_cpp(path: Path) -> str:
    path = Path(path)
    try:
        best = from_path(path).best()
        if best is not None:
            return str(best)
    except Exception:
        pass
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("latin-1", errors="replace")


# ============================================================
# 2. 打分：给候选 .cpp 排序
# ============================================================
def _score(f: Path, problem_name: str, filename: str | None) -> tuple:
    name, stem = f.name, f.stem
    lname, lstem = name.lower(), stem.lower()
    lprob = problem_name.lower()

    prob_sim  = SequenceMatcher(None, lstem, lprob).ratio()
    same_prob = 1 if lstem == lprob else 0

    if not filename:
        return (same_prob, prob_sim, -len(name), name)

    fn       = filename
    lfn      = fn.lower()
    lfn_stem = Path(fn).stem.lower()

    exact_name    = 1 if name == fn else 0
    exact_name_ci = 1 if lname == lfn else 0
    exact_stem    = 1 if lstem == lfn_stem else 0
    contains_stem = 1 if lfn_stem and (lfn_stem in lstem or lstem in lfn_stem) else 0
    contains_full = 1 if lfn       and (lfn       in lname or lname in lfn)      else 0

    sim = max(
        SequenceMatcher(None, lfn, lname).ratio(),
        SequenceMatcher(None, lfn_stem, lstem).ratio(),
    )

    return (
        exact_name, exact_name_ci, exact_stem,
        contains_stem, contains_full,
        round(sim, 6), same_prob, prob_sim,
        -len(name), name,
    )


def _pick_cpp(cpps: list[Path],
              problem_name: str,
              filename: str | None = None,
              min_score: float | None = None) -> Path:
    if not cpps:
        raise ValueError("cpps 为空")

    ranked = sorted(cpps, key=lambda f: _score(f, problem_name, filename),
                    reverse=True)
    best = ranked[0]

    if min_score is not None and filename:
        sim = max(
            SequenceMatcher(None, Path(filename).stem.lower(), best.stem.lower()).ratio(),
            SequenceMatcher(None, filename.lower(), best.name.lower()).ratio(),
        )
        if sim < min_score:
            raise ValueError(
                f"没有与 '{filename}' 足够相似的文件"
                f"（最高相似度 {sim:.2f} < {min_score}）"
            )
    return best


# ============================================================
# 3. 读单个题目
# ============================================================
def read_problem(problem_dir, filename=None, min_score=None, verbose=False):
    d = Path(problem_dir)
    if not d.is_dir():
        return None
    cpps = sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() == ".cpp")
    if not cpps:
        if verbose:
            print(f"[跳过] {d.name} 内没有可读 .cpp（{d}）")
        return None
    try:
        picked = _pick_cpp(cpps, d.name, filename, min_score)
    except ValueError as e:
        if verbose:
            print(f"[跳过] {d}: {e}")
        return None
    return picked, read_cpp(picked)


# ============================================================
# 4. 套娃考生目录识别
# ============================================================
def _looks_like_student(name: str) -> bool:
    up = name.upper()
    return up.startswith(("HE-J", "HE-S", "HE-"))


# ============================================================
# 5. 读考生的所有题目
# ============================================================
def read_examinee(examinee_dir, filename=None, min_score=None,
                  verbose=False, _depth=0):
    d = Path(examinee_dir)
    if not d.is_dir():
        return {}
    if _depth > 3:
        if verbose:
            print(f"[警告] 递归过深，停止于 {d}")
        return {}

    result = {}
    for sub in sorted(d.iterdir()):
        if (not sub.is_dir()
                or sub.name.startswith((".", "_"))
                or sub.name == "__MACOSX"):
            continue

        if _looks_like_student(sub.name):
            if verbose:
                print(f"[修正] {d.name}/{sub.name} 是嵌套考生，递归读取")
            inner = read_examinee(sub, filename=filename,
                                  min_score=min_score,
                                  verbose=verbose, _depth=_depth + 1)
            result.update(inner)
            continue

        r = read_problem(sub, filename=filename, min_score=min_score,
                         verbose=False)
        if r is not None:
            result[sub.name] = r
        elif verbose:
            print(f"[跳过] {sub.name} 内没有可读 .cpp（{sub}）")
    return result


# ============================================================
# 6. 读整场所有考生
# ============================================================
def read_all_examinees(csp_dir, filename=None, min_score=None, verbose=False):
    csp_dir = Path(csp_dir)
    if not csp_dir.is_dir():
        return {}
    out = {}
    for s in sorted(csp_dir.iterdir()):
        if (not s.is_dir()
                or s.name.startswith((".", "_"))
                or s.name == "__MACOSX"):
            continue
        out[s.name] = read_examinee(s, filename=filename,
                                    min_score=min_score, verbose=False)
    return out


# ============================================================
# 7. 兼容旧接口
# ============================================================
def open_target(path, filename=None):
    p = Path(path)
    if not p.exists():
        print(f"[错误] 路径不存在：{p}")
        return None
    if p.is_file():
        return (p, read_cpp(p)) if p.suffix.lower() == ".cpp" else None
    if not p.is_dir():
        return None

    own = sorted(f for f in p.iterdir()
                 if f.is_file() and f.suffix.lower() == ".cpp")
    if own:
        picked = _pick_cpp(own, p.name, filename)
        return picked, read_cpp(picked)

    for sub in sorted(p.iterdir()):
        if not sub.is_dir():
            continue
        r = read_problem(sub, filename)
        if r is not None:
            return r
    print(f"[信息] 未在 {p} 下找到任何 .cpp")
    return None


# ============================================================
# 8. 代码内容检查
# ============================================================
def _strip_comments(text: str) -> str:
    """剥离 // 行注释和 /* */ 块注释（不处理字符串内的伪注释）。"""
    out_lines = []
    in_block = False
    for line in text.splitlines():
        i, buf = 0, []
        while i < len(line):
            if in_block:
                end = line.find("*/", i)
                if end == -1:
                    break
                in_block = False
                i = end + 2
                continue
            p_line  = line.find("//", i)
            p_block = line.find("/*", i)
            if p_block != -1 and (p_line == -1 or p_block < p_line):
                buf.append(line[i:p_block])
                in_block = True
                i = p_block + 2
            elif p_line != -1:
                buf.append(line[i:p_line])
                break
            else:
                buf.append(line[i:])
                break
        out_lines.append("".join(buf))
    return "\n".join(out_lines)


def _compile_rules(rules, ignore_case: bool) -> dict:
    """把 list 或 dict 统一成 {category: [(原始关键字, 匹配器)]}。"""
    if isinstance(rules, dict):
        rule_map = rules
    else:
        rule_map = {"_default": list(rules)}

    compiled = {}
    for cat, kws in rule_map.items():
        items = []
        for kw in kws:
            if not isinstance(kw, str):
                raise ValueError(f"规则必须是字符串，实际为 {type(kw).__name__}: {kw!r}")
            if kw.startswith("re:"):
                flags = re.IGNORECASE if ignore_case else 0
                try:
                    pat = re.compile(kw[3:], flags)
                except re.error as e:
                    raise ValueError(f"正则编译失败 '{kw}': {e}")
                items.append((kw, pat))
            else:
                needle = kw.lower() if ignore_case else kw
                items.append((kw, ("substr", needle)))
        compiled[cat] = items
    return compiled


def validate_rules(rules, ignore_case=False) -> tuple[bool, str | None]:
    """验证规则能否编译，返回 (True, None) 或 (False, 错误信息)。"""
    try:
        _compile_rules(rules, ignore_case)
        return True, None
    except ValueError as e:
        return False, str(e)


def analyze_code(code: str,
                 rules: list[str] | dict[str, list[str]],
                 *,
                 ignore_case: bool = False,
                 strip_comments: bool = False) -> dict:
    if strip_comments:
        code = _strip_comments(code)

    try:
        compiled = _compile_rules(rules, ignore_case)
    except ValueError as e:
        print(f"[错误] 规则编译失败，跳过该文件：{e}")
        return {"matched": False, "total_hits": 0, "details": {}}

    details  = {cat: {} for cat in compiled}
    total_hits, matched = 0, False

    for lineno, line in enumerate(code.splitlines(), 1):
        hay_lower = line.lower() if ignore_case else line
        for cat, items in compiled.items():
            for original, matcher in items:
                if isinstance(matcher, tuple):
                    hit = matcher[1] in hay_lower
                else:
                    hit = matcher.search(line) is not None
                if hit:
                    details[cat].setdefault(original, []).append(lineno)
                    total_hits += 1
                    matched = True

    return {"matched": matched, "total_hits": total_hits, "details": details}


# ============================================================
# 9. 规则加载（含特殊字符支持）
# ============================================================
def load_rules(rules_arg: str | None,
               rules_file: str | None) -> list | dict | None:
    """
    从命令行字符串或规则文件加载规则。

    - --rules "a,b,c"       → list[str]；支持 \\, 转义逗号
    - --rules-file *.json   → list 或 dict
    - --rules-file *.txt    → 一行一条；注释只认 "# " 或 "##"
                              （#include / #define / #pragma 不会被当成注释）
    """
    if rules_arg:
        # \, → 占位符 → 分 → 还原，保护规则内部的逗号
        raw = rules_arg.replace("\\,", "\x00")
        items = [s.replace("\x00", ",").strip() for s in raw.split(",")]
        return [s for s in items if s]

    if rules_file:
        p = Path(rules_file)
        if not p.is_file():
            raise FileNotFoundError(f"规则文件不存在：{p}")
        text = p.read_text(encoding="utf-8-sig")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            out = []
            for line in text.splitlines():
                s = line.strip()
                if not s:
                    continue
                # 注释：只认 "# "（井号+空格/制表）或 "##"
                if s.startswith("##"):
                    continue
                if len(s) >= 2 and s[0] == "#" and s[1] in (" ", "\t"):
                    continue
                out.append(s)
            return out
    return None