"""T-032 终端接力：把 handoff 上下文 + 一个问题交给 `dsh --profile headless`。

设计要点：
- **不走 shell**：用 subprocess 的列表参数调用，问题里带 `; rm -rf /` 之类也不会被解释；
- prompt 是一个**独立参数**，不做任何字符串拼接解释；
- prompt 超 30000 字符就截断，并且**注明截断**——但要保证问题本身不被截掉；
- dsh 没装 / 超时 / 非零退出，都变成中文 ChatError，不抛原始异常给用户看。

**cmd.exe 会吃掉参数里的换行（2026-09-29 实测修）**：

Windows 上 dsh 是 npm 装的 `dsh.CMD`，原先一律经 `cmd.exe /c` 起它。但 cmd 把参数里的
`\n` 当**命令分隔符**——多行的接力上下文从**第一个换行处**被切断，五段正文与
`【我的问题】…` 整段消失，而 `returncode` 仍是 **0**、stderr 空 →
`chat_once` 的失败检查**完全不触发**，用户只看到答非所问（静默失败）。

现在 `build_dsh_command` 首选**解析 npm shim、直接起 `node.exe + bin.js`**（CRT 参数解析
不把 LF 当分隔符，换行完整保留）；解析不出才退回 `cmd.exe /c`，并把 prompt 折成单行
（折行时注明）。实测对照：`cmd /c` + 多行 → 靶子只收到第一个换行前 6 个字符；
`node + bin.js` + 多行 → 42 字符全部收到。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

from .handoff import handoff_dir, handoff_path, task_file_id
from .silent import silent_kwargs


class ChatError(Exception):
    """终端接力失败（缺上下文、缺 dsh、调用失败等）。"""


# prompt 上限：超过就截断（与任务卡一致）
MAX_PROMPT_CHARS = 30000
# 单次问答的超时上限（秒）：headless 一轮可能要跑很久，给足时间
DEFAULT_TIMEOUT_SECONDS = 600

TRUNCATED_NOTICE = "\n\n【说明】上面的上下文超过 {limit} 字符，已截断——只保留了前 {kept} 字符。"


def read_handoff(profile_dir: Path | str, when: str) -> str:
    """读某个任务的接力上下文；没有就提示用户先去点按钮。"""
    stamp = str(when or "").strip()
    if not stamp:
        raise ChatError("chat 需要给出任务时间戳，例如：chat \"2026-09-27 10:00\" \"我的代码哪里不足？\"")

    target = handoff_path(profile_dir, stamp)
    if not target.is_file():
        raise ChatError(
            f"找不到接力上下文：{target.name}（在 {handoff_dir(profile_dir)} 下）。"
            "先去看板任务卡片上点「在 DSH 中继续」生成它，再回来问。"
        )
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ChatError(f"读取接力上下文失败：{target}（{type(exc).__name__}）") from None


def assemble_prompt(context: str, question: str) -> str:
    """把「上下文 + 问题」拼成**一段** prompt；超长截断但保住问题。"""
    ask = str(question or "").strip()
    if not ask:
        raise ChatError("请给出要问的问题，例如：chat \"2026-09-27 10:00\" \"我该看书的哪部分？\"")

    body = str(context or "").strip()
    head = "下面是这道练习的接力上下文，请据此回答我的问题：\n\n"
    tail = f"\n\n【我的问题】{ask}\n"

    fixed = len(head) + len(tail)
    if fixed + len(body) <= MAX_PROMPT_CHARS:
        return head + body + tail

    # 需要截断：先给"截断说明"留位置，剩下才是能保留的上下文长度。
    # 注意：说明里要写"保留了前 N 字符"，而这个 N 正是我们要算的数——
    # 先按**最坏长度**（位数取上限 + 余量）留位，再算 N，避免算完超限（曾差 4 个字符）。
    worst = TRUNCATED_NOTICE.format(limit=MAX_PROMPT_CHARS, kept="9" * 8)
    room = MAX_PROMPT_CHARS - fixed - len(worst) - 1
    if room < 0:
        # 极端情况：问题本身太长，至少把问题完整留下
        return head + body[: max(0, MAX_PROMPT_CHARS - fixed)] + tail
    kept = body[:room]
    notice = TRUNCATED_NOTICE.format(limit=MAX_PROMPT_CHARS, kept=len(kept))
    prompt = head + kept + notice + tail
    # 兜底：万一还是超（语言/换行差异），硬裁到上限，保证契约成立
    return prompt[:MAX_PROMPT_CHARS] if len(prompt) > MAX_PROMPT_CHARS else prompt


def find_dsh() -> str | None:
    """找 dsh 可执行文件；找不到返回 None（调用方给中文提示）。"""
    found = shutil.which("dsh")
    if found:
        return found
    # Windows 上 shutil.which 对 .cmd 有时看不见，再补一手
    if os.name == "nt":
        for name in ("dsh.cmd", "dsh.exe", "dsh.ps1"):
            found = shutil.which(name)
            if found:
                return found
    return None


# --- Windows 传参：绕开 cmd.exe 的换行截断 ---------------------------------

_SHIM_PROG_RE = re.compile(r'SET\s+"?_prog=([^"\r\n]+)"?\s*$', re.I | re.M)
_SHIM_ENTRY_RE = re.compile(r'"%_prog%"\s+"([^"]+\.js)"', re.I)
_CRLF_RUN_RE = re.compile(r"[ \t]*[\r\n]+[ \t]*")

FLATTEN_NOTICE = "【说明】当前环境只能经 cmd.exe 传参（它不允许参数带换行），上下文已折成单行。"


def _resolve_npm_shim_entry(shim: str) -> tuple[str, str] | None:
    """解析 npm 生成的 Windows shim（如 dsh.cmd），取出 (node.exe, bin.js) 真实入口。

    npm shim 骨架固定，最后一行形如：

        endLocal & ... & "%_prog%"  "%dp0%\\node_modules\\<pkg>\\lib\\bin.js" %*

    直接起 `node bin.js` 可以**完全绕开 cmd.exe**：cmd 把参数里的换行当**命令分隔符**
    （实测多行 prompt 被切到第一个换行之前），node 走 CRT 参数解析，换行原样保留。

    解析不出、或 node/bin.js 任一个不存在 → None（调用方退回 cmd 路径）。
    """
    try:
        text = Path(shim).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    match = _SHIM_ENTRY_RE.search(text)
    if not match:
        return None

    here = Path(shim).parent
    raw_entry = match.group(1).replace("%dp0%", str(here)).replace("%~dp0", str(here))
    entry = Path(raw_entry)
    if not entry.is_file():
        return None

    prog_matches = _SHIM_PROG_RE.finditer(text)
    candidates = [match.group(1).strip() for match in prog_matches] or ["node"]
    # shim 里 `%_prog%` 有**两个候选分支**：IF EXIST "%dp0%\node.exe" 用本目录的 node，
    # ELSE 用 PATH 里的 `node`。真机（node 装在 C:\Program Files\nodejs）走的是 ELSE，
    # 所以必须**按顺序取第一个可用候选**，只认第一个会误判成解析失败。
    node: str | None = None
    for prog in candidates:
        prog = prog.replace("%dp0%", str(here)).replace("%~dp0", str(here))
        if prog.lower().endswith((".exe", ".cmd", ".bat")):
            if Path(prog).is_file():
                node = prog
                break
        else:
            node = shutil.which(prog)
            if node:
                break
    if not node:
        return None
    return node, str(entry)


def _flatten_for_cmd(text: str) -> str:
    """把 prompt 折成单行——cmd.exe 的参数里不能有换行（会被当命令分隔符切断）。

    只在**退不回 node 直起**、必须走 cmd 的降级路径上用；确实折过行就**明说**，
    不静默改动材料（与项目「缺数据给占位说明」的约定一致）。
    """
    original = str(text or "")
    flat = _CRLF_RUN_RE.sub(" ", original).strip()
    if "\n" in original or "\r" in original:
        return FLATTEN_NOTICE + " " + flat
    return flat


def build_dsh_command(executable: str, prompt: str) -> list[str]:
    """构造命令行：**列表参数**，prompt 是最后一个独立参数。

    Windows 上 npm 装的 dsh 是 `dsh.CMD`（批处理），CreateProcess **不能直接执行它**
    ——实测报 FileNotFoundError。两条路，按可靠性排序：

    1. **解析 shim，直接起 `node.exe + bin.js`**（首选）：不经过 cmd.exe，prompt 里的
       换行完整保留（cmd 会把换行当**命令分隔符**，把多行上下文从第一个换行处切断）。
    2. **退回 `cmd.exe /c dsh.CMD`**（shim 解析不出来时）：这仍然**不是 shell 注入面**
       （prompt 依旧是列表里一个独立参数），但必须先把换行折成单行，否则会被静默截断。
    """
    target = str(executable)
    if os.name == "nt" and target.lower().endswith((".cmd", ".bat")):
        direct = _resolve_npm_shim_entry(target)
        if direct is not None:
            node, entry = direct
            return [node, entry, "--profile", "headless", str(prompt)]
        comspec = os.environ.get("COMSPEC") or "cmd.exe"
        return [comspec, "/c", target, "--profile", "headless", _flatten_for_cmd(prompt)]
    return [target, "--profile", "headless", str(prompt)]


def headless_persona_override(home: Path | str | None = None) -> str | None:
    """检查 headless profile 是否被配了 persona 覆盖（会压过我们送进去的上下文）。

    实测：本机 "~/.dsh/profiles/headless/cordis.patch.yml" 里有 personaPrefix
    （「你是 ENI。不是 coding agent…」）。这种 profile 会把 CLI 传进去的文本
    当成"一条消息"处理，但人设要求它先自我介绍、并要求用户把材料再贴一次，
    于是**接力上下文的利用率很差**——用户看到的答案会跑偏。

    这不是我们要"修"的东西（那是用户的全局 DSH 配置），但**必须如实告诉用户**。
    """
    import os as _os

    root = Path(home) if home else Path(_os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))
    patch = root / "profiles" / "headless" / "cordis.patch.yml"
    if not patch.is_file():
        return None
    try:
        text = patch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r"^\s*personaPrefix\s*:\s*\|?\s*$", text, re.M)
    return str(patch) if match else None


# ANSI 颜色/光标控制码：stderr 的推理流常带，展示前清掉
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class ChatReply(str):
    """一次调用的结果。

    **是 str 的子类**：老调用方（T-032/T-034）把它当字符串用照旧能跑，
    新调用方（T-037）可以读 .answer 与 .thinking。
    """

    def __new__(cls, answer: str, thinking: str = ""):
        obj = super().__new__(cls, answer)
        obj.answer = answer
        obj.thinking = thinking
        return obj


def chat_once(
    executable: str,
    prompt: str,
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ChatReply:
    """调一次 dsh headless，返回答案 + 思考过程。

    答案取 stdout；**思考流取 stderr，两者绝不混**（T-037）：
    混在一起会让推理过程被当成答案正文渲染进面板。
    """
    command = build_dsh_command(executable, prompt)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            # 关键：不走 shell。问题里有 `; rm -rf /` 也只是普通文本。
            shell=False,
            # T-041：静默执行——Windows 上不弹控制台窗口（跑测试时尤其重要）
            **silent_kwargs(),
        )
    except FileNotFoundError:
        raise ChatError(
            f"找不到可执行的 dsh（{executable}）：请先安装 DeepSeek Harness（npm i -g @deepseek-ai/dsh），"
            "或确认 dsh 在 PATH 里。"
        ) from None
    except subprocess.TimeoutExpired:
        raise ChatError(f"dsh headless 超时（超过 {timeout} 秒）：可以稍后重试，或把问题拆小一点。") from None
    except OSError as exc:
        raise ChatError(f"调用 dsh 失败：{type(exc).__name__}") from None

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ChatError(f"dsh headless 退出码 {completed.returncode}：{detail[:400] or '(没有更多信息)'}")
    answer = completed.stdout or ""
    thinking = _ANSI_RE.sub("", completed.stderr or "").strip()
    return ChatReply(answer, thinking)