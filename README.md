# CSP 考生代码批量读取与检查工具

批量读取 CSP-J / CSP-S 考生源代码，统计缺题情况、检查代码内容。
支持**命令行（CLI）** 和 **图形界面（GUI）** 两种模式，功能完全等价。 **注：大量使用了DeepSeek以编写！（包括这个解释说明）**

---

## 目录

- [下载](#下载)
- [功能总览](#功能总览)
- [快速开始](#快速开始)
- [目录结构约定](#目录结构约定)
- [GUI 使用](#gui-使用)
- [CLI 使用](#cli-使用)
- [检查规则](#检查规则)
- [快捷键速查](#快捷键速查)
- [输出解读](#输出解读)
- [特殊字符处理](#特殊字符处理)
- [常见问题](#常见问题)
- [文件清单](#文件清单)

---

## 下载

- 百度网盘链接: https://pan.baidu.com/s/1nyKMzUzg5Ko0DpYCr_jg7w 提取码: ccf6
- Github: 就在这里😄



## 功能总览

### 读取

- ✅ 批量读取 CSP-J / CSP-S 全部考生的 `.cpp`
- ✅ **自动检测编码**：UTF-8 / UTF-8-BOM / GBK / GB18030 / 未知编码兜底
- ✅ **自动识别题名**：从数据统计频率 ≥20% 的目录名，J 组 / S 组无需改代码
- ✅ **自动修正 typo**：`travle` → `travel`、`srting` → `string`、`cards` → `card`
- ✅ **处理套娃目录**：`HE-J00424/HE-J00424/travel/...` 递归合并
- ✅ **智能挑 .cpp**：多 `.cpp` 时按"精确 → 忽略大小写 → 主名一致 → 包含 → 相似度"打分
- ✅ **可中断**：GUI 有"停止"按钮，考生级检查点，秒级响应
- ✅ **进度反馈**：每 200 名考生打印一次进度

### 统计（读取模式）

- ✅ 4 题齐全 / 有缺题 的人数与占比
- ✅ 各题缺交人数（横向）
- ✅ 缺题数量分布（纵向：缺 1 题 / 2 题 / 3 题 / 4 题）
- ✅ typo 修正记录

### 检查（检查模式）

- ✅ 逐行扫描，支持**子串**和**正则**两种匹配
- ✅ **分类规则**：JSON 字典组织关键字，按类别统计
- ✅ **可选剥离注释**：`//` 和 `/* */`（默认关闭）
- ✅ **可选忽略大小写**
- ✅ **导出 JSON**：含每个考生的命中题目、文件路径、具体行号
- ✅ **坏正则不崩溃**：预检规则，失败时只报错不中断

### 界面

- ✅ CLI：完整参数，可脚本化、可定时任务
- ✅ GUI：Tkinter，所有 CLI 参数都有对应控件
- ✅ **停止按钮**：软中断
- ✅ **显示等价命令**：GUI 配置一键转 CLI 命令
- ✅ **帮助 / 关于**：F1 打开，详细解释每个字段和按钮

---

## 快速开始

### 1. 安装依赖

```powershell
pip install charset-normalizer
```

> Python 3.9+，Tkinter 官方版自带（Linux 需要 `sudo apt install python3-tk`）。

### 2. 启动

```powershell
# GUI（不带参数）
python main.py

# CLI（带路径）
python main.py "D:/CSP/End/CSP-J"
```

### 3. 典型工作流

```
① 读取模式看数据完整性
   python main.py "D:/CSP/End/CSP-J"
   → 确认题名识别正常、缺题率合理

② 单考生试点验证规则
   python main.py "D:/CSP/End/CSP-J" --check --student HE-J00001 --rules-file rules.json -v

③ 全量检查，导出 JSON
   python main.py "D:/CSP/End/CSP-J" --check --rules-file rules.json --strip-comments --export hits.json

④ 用 Python / Excel 分析 hits.json
```

---

## 目录结构约定

```
CSP-J/
├── HE-J00001/
│   ├── travel/
│   │   └── travel.cpp
│   ├── string/
│   │   └── string.cpp
│   ├── and/
│   │   └── and.cpp
│   └── card/
│       └── card.cpp
├── HE-J00002/
│   └── ...
└── HE-J00003/
    └── ...
```

**程序对以下"异常结构"自动兼容**：

| 情况 | 处理 |
|---|---|
| 目录名 typo（`travle`、`srting`、`cards`） | 自动归一化到标准题名 |
| 套娃（`HE-J00424/HE-J00424/...`） | 递归合并到外层考生 |
| 题目文件夹空（未交） | 记为缺题 |
| 题目目录名带扩展名（`string.cpp/`） | 自动归一化 |
| 无 `.cpp` 但有 `.cc`/`.cxx` | 当前只认 `.cpp`（可按需扩展） |
| 空考生文件夹 | 计为缺 4 题（弃考） |

---

## GUI 使用

### 启动

```powershell
python main.py
python main.py --gui     # 强制启动
```
或直接运行main.cpp。

### 界面分区

```
┌───────────────────────────────────────────────────────┐
│ 文件  帮助                            ← 菜单栏         │
├───────────────────────────────────────────────────────┤
│ 数据位置                                              │
│  比赛根目录  [________________________] [浏览...][打开]│
│  考生(可选)  [__________]  题目(可选) [__________]     │
│  题名(可选)  [__________]  .cpp文件名 [__________]     │
│  最小相似度  [___]  (留空=不限制，范围 0~1)            │
│  预览字符数  [___]  (单题预览长度，0=不显示)           │
├───────────────────────────────────────────────────────┤
│ 模式                                                  │
│  (o) 读取统计  ( ) 内容检查        [ ] 详细日志(-v)   │
├───────────────────────────────────────────────────────┤
│ [▶ 开始执行] [■ 停止] [🗑 清空输出] [📋 显示等价命令]   │
│ [❓ 帮助]  [████████═══════════════════════════]      │
├───────────────────────────────────────────────────────┤
│ 检查规则与选项（仅"内容检查"模式显示）               │
│  [文本框: freopen\nsystem\nwhile(1)]                  │
│  [加载规则文件...] [清空规则] [示例JSON]              │
│  [ ]忽略大小写 [ ]剥离注释  导出到:[_______] [...]    │
├───────────────────────────────────────────────────────┤
│ 输出                                                  │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │
│  ▓  [信息] 比赛根目录：...                            │
│  ▓  [完成] 共处理 1972 名考生                         │
│  ▓  ...                                               │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │
├───────────────────────────────────────────────────────┤
│ 状态: 完成                                            │
└───────────────────────────────────────────────────────┘
```

### 字段速查

| 字段 | 必填 | 说明 |
|---|---|---|
| 比赛根目录 | ✅ | 支持绝对/相对路径、`~`、拖拽、带空格 |
| 浏览... | — | 打开文件夹选择对话框 |
| 打开 | — | 用资源管理器打开路径 |
| 考生(可选) | — | 留空 = 全部考生 |
| 题目(可选) | — | 需配合"考生"使用 |
| 题名(可选) | — | 留空 = 自动检测 |
| .cpp文件名 | — | 留空 = 自动挑选 |
| 最小相似度 | — | 留空 = 不限制（总挑最像）；0~1 |
| 预览字符数 | — | 默认 80，0 = 只显示路径 |
| 详细日志(-v) | — | 默认关；开启后输出更啰嗦 |
| 忽略大小写 | — | 默认关；C++ 区分大小写 |
| 剥离注释 | — | **默认关**；开启后先剥离 `//` 和 `/* */` |
| 导出到 | — | 检查模式下保存 JSON |

### 帮助与关于

- **F1** 或 **帮助 → 使用说明**：打开详细帮助
- **帮助 → 关于**：版本、功能、依赖、结构

帮助窗口内每个控件都有独立段落说明"是什么、干什么、什么时候用"。

---

## CLI 使用

### 命令格式

```powershell
python main.py [路径] [选项]
```

不传路径 → 启动 GUI。

### 参数总表

| 参数 | 类型 | 说明 |
|---|---|---|
| `root` | 位置参数 | 比赛根目录；不给则启动 GUI |
| `--gui` | flag | 强制启动 GUI |
| `--student NAME` | str | 只看某个考生 |
| `--problem NAME` | str | 只看某题（配合 `--student`） |
| `--problems A,B,C,D` | str | 手动指定题名 |
| `--filename FILE` | str | 优先匹配的 .cpp 文件名 |
| `--min-score FLOAT` | float | 相似度阈值（0~1） |
| `--show-code N` | int | 单题预览字符数（默认 80） |
| `-v` / `--verbose` | flag | 详细日志 |
| `--check` | flag | 进入检查模式 |
| `--rules "a,b,c"` | str | 检查规则（逗号分隔；支持 `\,` 转义） |
| `--rules-file FILE` | str | 从文件加载规则 |
| `--ignore-case` | flag | 忽略大小写 |
| `--strip-comments` | flag | 剥离注释（默认关闭） |
| `--export OUT.json` | str | 导出检查结果 |

### 常用命令

```powershell
# ── 读取模式 ─────────────────────────────────
python main.py "D:/CSP/End/CSP-J"
python main.py "D:/CSP/End/CSP-S"
python main.py "D:/CSP/End/CSP-S" --problems lockout,slime,arena,xxx
python main.py "路径" --student HE-J00001
python main.py "路径" --student HE-J00001 --problem travel
python main.py "路径" --student HE-J00001 --show-code 500
python main.py "路径" -v

# ── 检查模式 ─────────────────────────────────
python main.py "路径" --check --rules "freopen,system"
python main.py "路径" --check --rules-file rules.json
python main.py "路径" --check --rules-file rules.json -v
python main.py "路径" --check --rules-file rules.json --strip-comments --export hits.json
python main.py "路径" --check --student HE-J00032 --rules-file rules.json -v

# ── 帮助 ─────────────────────────────────────
python main.py --help
```

---

## 检查规则

### 规则写法（四种）

#### 1. 一行一条（TXT 文件 / GUI 文本框）

```
freopen
system
while(1)
```

#### 2. 逗号分隔（`--rules` 参数）

```powershell
--rules "freopen,system,while(1)"
```

规则本身含逗号时用 `\,` 转义：

```powershell
--rules "re:pair<int\,int>,system"
```

#### 3. JSON 字典（分类）

```json
{
  "危险函数": ["system", "popen", "exec"],
  "文件操作": ["freopen", "fopen"],
  "死循环":   ["while(1)", "for(;;)"]
}
```

#### 4. 正则（`re:` 前缀）

```json
{
  "死循环":   ["re:while\\s*\\(\\s*1\\s*\\)"],
  "可疑跳转": ["re:\\bgoto\\b"]
}
```

### 完整示例 `rules.json`

```json
{
  "危险函数": ["system", "popen", "exec", "fork", "gets"],
  "文件操作": ["freopen", "fopen", "ifstream", "ofstream"],
  "死循环":   ["while(1)", "while(true)", "for(;;)", "re:while\\s*\\(\\s*1\\s*\\)"],
  "禁用头文件": ["#include<bits/stdc++.h>", "#include<windows.h>"],
  "可疑跳转": ["re:\\bgoto\\b"],
  "中文标记": ["样例输入", "题目要求"]
}
```

### 特殊字符处理

| 字符 | 处理方式 | 示例 |
|---|---|---|
| `#` | TXT 里注释用 `# `（带空格）或 `##`，`#include` 安全 | `#include<bits/stdc++.h>` |
| `,` | `--rules` 支持 `\,` 转义 | `re:pair<int\,int>` |
| `"` | JSON 里用 `\"`；GUI 里原样 | `"cout << \"hello\""` |
| `\` | JSON 里双写 `\\`；正则按标准语法 | `"re:\\d+"` |
| 中文 | UTF-8 全程支持 | `"样例输入"` |
| 坏正则 | 预检失败时打印具体错误，不崩溃 | `re:[unclosed` → 报错退出 |

### TXT 文件注释规范

**推荐**：

```
# 这是一条注释（# + 空格，会被忽略）
## 这也是一条注释（## 开头，会被忽略）
freopen
#include<bits/stdc++.h>
system
```

**注意**：`#include` 后紧跟字母，**不会**被当成注释（只有 `# ` 和 `##` 才是注释）。

---

## 快捷键速查

### 全局

| 快捷键 | 功能 |
|---|---|
| `F1` | 打开使用说明（在帮助/关于窗口里则关闭该窗口） |
| `Ctrl+R` | 开始执行 |
| `Esc` | 清空输出（帮助/关于窗口里则关闭窗口） |

### 输出区

| 快捷键 | 功能 |
|---|---|
| `Ctrl+A` | 全选 |
| `Ctrl+C` | 复制 |
| 鼠标拖选 | 选中局部 |
| 鼠标滚轮 | 滚动 |

### 文件对话框

| 快捷键 | 功能 |
|---|---|
| `Ctrl+L` | 输入路径跳转（部分系统） |
| `Enter` | 确认 |
| `Esc` | 取消 |

---

## 输出解读

### 读取模式输出示例

```
[信息] 比赛根目录：D:\CSP\End\CSP-J

[完成] 共处理 1972 名考生
[信息] 自动识别标准题名（4 个）：['travel', 'string', 'and', 'card']

================================================================
[统计] 总考生 1972 人
       全部4题齐全 1666 人 (84.5%)      ← 4 题都交了
       有缺题        306 人 (15.5%)      ← 至少缺 1 题

[各题缺交人数]                        ← 横向：每道题多少人没交
  travel     缺   17 人  (交 1955)
  string     缺   57 人  (交 1915)
  and        缺  122 人  (交 1850)
  card       缺  265 人  (交 1707)    ← 这题缺交最多

[缺题数量分布]                        ← 纵向：每人缺几题
  缺 1 题:  202 人                    ← 大部分人只缺 1 题
  缺 2 题:   67 人
  缺 3 题:   23 人
  缺 4 题:   14 人                    ← 完全弃考

[typo 修正] 12 处：
  HE-J00273: 'srting' → 'string'
  HE-J00404: 'cards' → 'card'
  ...

[前 20 名考生预览]
  HE-J00001        → ['and', 'card', 'string', 'travel']
  ...
```

**自洽性验证**：

- 各题缺交人数之和 = Σ(缺 k 题 × 人数) = 总缺题单位
- 缺 k 题人数之和 = 有缺题总人数

### 检查模式输出示例

```
[信息] 已读取 1972 名考生的代码

================================================================
[检查] 共检查 1972 名考生
       命中考生 38 人 (1.9%)         ← 有多少人任意规则命中

[规则命中统计]
  freopen                     命中   32 次   ← 32 个"考生-题目"单位含 freopen
  system                      命中   10 次
  while(1)                    命中    6 次

[按分类]
  危险函数         命中考生   12 人
  文件操作         命中考生   32 人
  死循环           命中考生    6 人

[命中明细]（前 30 名考生）        ← 加 -v 才显示
  HE-J00032
    [文件操作] freopen →  card    行 [12, 45]
    [文件操作] freopen →  and     行 [10]
    [危险函数] system  →  travel  行 [3, 7, 9]
```

**注意**："命中 32 次"指 32 个**文件**含该关键字，不是 32 行。同一文件里 10 次 `freopen` 只算 1 次。

### 导出 JSON 结构

```json
{
  "total_students": 1972,
  "hit_students": 38,
  "rule_counts": {
    "freopen": 32,
    "system": 10
  },
  "details": {
    "HE-J00032": {
      "文件操作": {
        "freopen": [
          {"problem": "card", "path": "...card.cpp", "lines": [12, 45]},
          {"problem": "and",  "path": "...and.cpp",  "lines": [10]}
        ]
      },
      "危险函数": {
        "system": [
          {"problem": "travel", "path": "...travel.cpp", "lines": [3, 7, 9]}
        ]
      }
    }
  }
}
```

二次分析：

```python
import json
data = json.load(open("hits.json", encoding="utf-8"))

# 谁用了 system
for sid, cats in data["details"].items():
    if "危险函数" in cats and "system" in cats["危险函数"]:
        print(sid, cats["危险函数"]["system"])
```

---

## 特殊字符处理

| 场景 | 推荐做法 |
|---|---|
| `#include<bits/stdc++.h>` | 用 JSON 规则文件，或 TXT 里直接写（`#` 后跟 `<` 不算注释） |
| 规则本身含逗号 | 用 `--rules-file`；或 `--rules` 里写 `\,` |
| 规则含双引号 | 用 JSON 文件：`"cout << \"hello\""` |
| 正则 `\b` / `\d` | JSON 里双写：`"re:\\bgoto\\b"` |
| 中文关键字 | 规则文件存 UTF-8，终端设 UTF-8 编码 |
| 坏正则 | 预检时报具体错误并退出，不会让整场任务崩溃 |

**最稳妥的做法**：日常规则一律写进 `rules.json`，绕开所有命令行转义问题。

---

## 常见问题

### 安装 / 环境

**Q: `ModuleNotFoundError: charset_normalizer`？**

```powershell
pip install charset-normalizer
```

**Q: `ModuleNotFoundError: tkinter`（Linux）？**

```powershell
sudo apt install python3-tk
```

**Q: PowerShell 里路径带空格报"无法识别"？**

用 `&` 调用运算符 + 双引号：

```powershell
& "C:/Program Files/Python/python.exe" main.py "D:/我的数据/CSP-J"
```

或直接把文件夹拖进终端（自动带引号）。

### 使用

**Q: 100% 缺题 / 题名识别错？**

手动指定题名：

```powershell
python main.py "路径" --problems lockout,slime,arena,xxx
```

**Q: 大量 `[跳过]` 日志？**

默认静默，只有加 `-v` 才显示。没加 `-v` 时看到跳过日志说明不是最新版，更新 `main.py`。

**Q: 同一个路径第一次报不存在，第二次成功？**

路径里有不可见字符（`\u00A0` 非断空格、`\u200B` 零宽字符、`\ufeff` BOM）。当前版本已自动清洗。若仍出现，报错里的 `!r` 会显示原始字符。

**Q: 缺题人数怎么算的？**

- `[各题缺交人数]`：横向，每道题多少人没交
- `[缺题数量分布]`：纵向，每人缺几题
- 两者加权求和相等（461 = 461），是算法正确性验证

**Q: 怎么中途停止？**

GUI 点"■ 停止"；CLI 用 `Ctrl+C`。软中断粒度是"考生"，最坏延迟 <100ms。

**Q: GUI 和 CLI 结果不一致？**

点"📋 显示等价命令"，把输出的命令复制到终端执行，结果应完全一致。如果不一样，把两条命令和输出发出来。

### 检查模式

**Q: 为什么"命中 32 次"比预期少？**

"次"指"多少个考生-题目文件命中"，不是"多少行"。想看行号加 `-v`。

**Q: 剥离注释开着反而命中变少？**

规则本身是查注释（如 `// TODO`）时，剥离会把目标删掉。此时**关掉"剥离注释"**。

**Q: 规则里 `#include` 不生效？**

TXT 文件里注释用 `# `（带空格）或 `##`，当前版本 `#include` **不会**被当注释。如果还是不生效：

1. 确认 `main.py` / `core.py` 是最新版
2. 或用 JSON 格式规则文件

**Q: 忽略大小写什么时候用？**

C++ 是大小写敏感的（`System` ≠ `system`），一般**不开**。只有想"抓任何形式"时才勾。

---

## 文件清单

```
Confusing_Behavior_Finder2/
├── main.py          # 入口：CLI + GUI
├── core.py          # 核心：读取、编码检测、规则检查
├── rules.json       # （可选）检查规则
├── README.md        # 本文件
└── .venv/           # 虚拟环境
```

### `main.py` 结构

```
路径处理
  _clean / _to_dir

题名处理
  detect_standard_problems / normalize

读取模式
  report

检查模式
  run_check / _write_export

批量读取
  _read_all_with_stop

核心执行
  execute（CLI 和 GUI 共用）

CLI
  parse_args / main

GUI
  launch_gui
    ├── 数据位置
    ├── 模式
    ├── 执行按钮
    ├── 检查规则与选项
    ├── 输出区
    ├── 菜单栏
    └── 帮助 / 关于窗口
```

### `core.py` 结构

```
read_cpp                     # 自动编码读取
_score / _pick_cpp           # .cpp 打分挑选
read_problem                 # 读单题
read_examinee                # 读考生（含套娃）
read_all_examinees           # 读全量
open_target                  # 兼容旧接口
_strip_comments              # 剥离注释
_compile_rules               # 规则编译
validate_rules               # 规则预检
analyze_code                 # 代码检查核心
load_rules                   # 规则加载（含特殊字符处理）
```

---

## 依赖

| 依赖 | 版本 | 用途 |
|---|---|---|
| Python | 3.9+ | 需要 `str \| None` 语法 |
| charset-normalizer | 3.x | 自动检测文件编码 |
| tkinter | 内置 | GUI（Windows/macOS 官方版自带；Linux 单独装） |

---

## 提示

大量使用了DeepSeek来编写！

---

## 更新日志

### v1.0

- 初始版本：CLI + GUI
- 自动编码检测 / 题名识别 / typo 修正 / 套娃处理
- 读取统计 / 内容检查 / JSON 导出
- 停止按钮 / 显示等价命令 / 帮助 / 关于
- 特殊字符（`#` `,` `"` `\` 中文）全流程支持
- 剥离注释默认关闭
