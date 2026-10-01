# -*- coding: utf-8 -*-
"""对照任务卡逐条判分：LO 提交版 vs 最小修改版。只读、不改动任何项目文件。

条目分级（重要，v2 修正）：
  [验收n] = 任务卡「验收方式」原文，这一栏才决定过不过
  [要点n] = 任务卡「实现要点」原文，属于建议/升级项，不构成验收 FAIL
  [风格]  = PEP 8（PCC 第4章 Styling Your Code），不构成验收 FAIL
v1 把 [要点8]/[风格] 混进「验收方式」表里，导致判重；v2 拆开。
"""
import io
import sys
from contextlib import redirect_stdout

sys.stdout.reconfigure(encoding="utf-8")

# LO 提交原文（一字未改，空行已折叠）
SUBMITTED = '''
class_name =["小明","小红","小白","小蓝","小绿"]
print("自定义班级")
i = 1
for student_name in class_name:
    print(f"{i}.{student_name}")
    i += 1
print(f"共计{len(class_name)}人")
'''

# 最小修改版：三处空格 + enumerate 接管序号
FIXED = '''
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]
print("自定义班级")
for i, student_name in enumerate(class_name, start=1):
    print(f"{i}. {student_name}")
print(f"共计 {len(class_name)} 人")
'''


def run(src):
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            exec(compile(src, "roster.py", "exec"), {"__name__": "__main__"})
        return buf.getvalue().splitlines(), None
    except Exception as e:
        return buf.getvalue().splitlines(), f"{type(e).__name__}: {e}"


def grade(lines, src):
    """返回 [(条目, 是否通过, 证据)]"""
    names = ["小明", "小红", "小白", "小蓝", "小绿"]
    checks = []

    # [验收1] 一行标题
    checks.append(("[验收1] 一行标题，且最先输出",
                   len(lines) > 0 and lines[0] == "自定义班级",
                   repr(lines[0]) if lines else "无输出"))

    body = lines[1:-1] if len(lines) >= 2 else []

    # [验收2] 每个名字单独占一行
    checks.append(("[验收2] 每个名字各占一行（5 行名单）",
                   len(body) == 5, f"名单行数={len(body)}"))

    # [验收3] 序号 1..N 递增，无跳号
    ok_seq = all(ln.startswith(f"{i}.") for i, ln in enumerate(body, start=1))
    checks.append(("[验收3] 序号递增 1..5、无重复无错位", ok_seq, " | ".join(body)))

    # [验收4] 句式 `1. 张三`：验收方式原文写了点号后一个空格
    bad = [ln for ln in body if ". " not in ln]
    checks.append(("[验收4] 句式 `1. 张三`：点号后一个空格", not bad,
                   "全部含 '. '" if not bad else "点号后缺空格: " + " | ".join(bad)))

    got = [ln.split(". ", 1)[1] if ". " in ln else ln.split(".", 1)[-1] for ln in body]
    checks.append(("[验收4补] 名字与列表一一对应、无重复", got == names, f"{got}"))

    # [验收5] 末行总人数
    last = lines[-1] if lines else ""
    checks.append(("[验收5] 最后一行打印总人数",
                   last.strip().replace(" ", "") == "共计5人", repr(last)))

    # [验收6] 缩进自查点：总人数只输出一次
    cnt = sum(1 for ln in lines if "共计" in ln)
    checks.append(("[验收6] 总人数只输出 1 次（未被缩进进循环）",
                   cnt == 1, f"出现 {cnt} 次"))

    # [要点9] 名字改长度后仍对齐
    l2, _ = run(FIXED.replace("小绿", "欧阳小明"))
    b2 = l2[1:-1]
    drift = [x for x, y in zip(b2, b2[1:])
             if x.split(". ")[0] != str(int(y.split(". ")[0]) - 1)]
    checks.append(("[要点9] 混入长名字后序号列仍对齐", not drift, f"{b2}"))

    # [风格] PEP 8 空格 —— 建议项，不是验收项
    reasons = []
    if "class_name = [" not in src:
        reasons.append("`class_name =[` 等号后缺空格")
    if '"共计 ' not in src:
        reasons.append("`共计5人` f-string 大括号内缺空格")
    checks.append(("[风格] `=` 两侧与 f-string 大括号内空格统一", not reasons,
                   "两处空格齐" if not reasons else "；".join(reasons)))

    # [要点8] 序号该不该由循环自身产出——注入 continue 看序号漂不漂
    has_manual = "i += 1" in src and "enumerate" not in src
    drift_src = src
    for pat in ('    print(f"{i}.{student_name}")', '    print(f"{i}. {student_name}")'):
        drift_src = drift_src.replace(
            pat, '    if student_name == "小白":\n        continue\n' + pat)
    d_lines, _ = run(drift_src)
    d_body = [ln for ln in d_lines
              if ln.strip() and "自定义" not in ln and "共计" not in ln]
    expect = ["1. 小明", "2. 小红", "4. 小蓝", "5. 小绿"]
    checks.append(("[要点8] 跳过一人后序号仍等于名单位置", d_body == expect,
                   ("手动 i 版" if has_manual else "enumerate 版")
                   + "：跳过「小白」→ " + " | ".join(d_body)
                   + f"（enumerate 语义应为 {' | '.join(expect)}）"))

    return checks


for label, src in (("【提交版】", SUBMITTED), ("【最小修改版】", FIXED)):
    lines, err = run(src)
    print(f"\n===== {label} 实跑回包 (Python {sys.version.split()[0]}) =====")
    for ln in lines:
        print("  " + ln)
    if err:
        print("  !! " + err)
    print("----- 逐条判分 -----")
    results = grade(lines, src)
    for item, ok, ev in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {item}  <-- {ev}")
    acc = [x for x in results if x[0].startswith("[验收")]
    print(f"----- 验收方式原文 {len(acc)} 项：{sum(1 for x in acc if x[1])} PASS / "
          f"{sum(1 for x in acc if not x[1])} FAIL"
          f"（[要点]/[风格] 项不计入验收）-----")
