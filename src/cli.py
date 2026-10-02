"""命令行入口：参数解析 + 把各命令接到业务模块上（本身不含业务逻辑）。

命令一览见 USAGE / KNOWN_COMMANDS；看板（serve）的固定动作也在这里接线（_build_board）。
退出码约定：0 成功；1 运行失败（缺前置产物、LLM/飞书失败等）；2 参数错误（同时打印用法）。
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

from .credentials import DEFAULT_ENV_PATH, CredentialError, load_credentials
from .distill import DistillError, distill_note, format_points
from .feishu import FeishuApiError, FeishuClient, Transport
from .llm import PROVIDER_ALIASES, LLMClient, LLMError, config_for, read_env_values, resolve_provider
from .planner import (
    DEFAULT_STALE_DAYS,
    MIN_POINTS,
    PlannerError,
    append_task_record,
    generate_task,
    render_task,
)
from .profile import (
    KnowledgeProfile,
    ProfileError,
    mark_done,
    merge_points,
    normalize_point_name,
    resolve_point_name,
    touch_points,
    write_profile_atomic,
)
from .alignment import DEFAULT_ALIGNMENT_NAME, AlignmentError
from .syllabus import DEFAULT_SYLLABUS_PATH, SyllabusError, import_book
from .sync import sync_document_tree

USAGE = "\n".join(
    [
        "用法：",
        "  python -m src.cli sync <文档ID 或 wiki/docx 链接>",
        "  python -m src.cli distill <笔记文件>|--all [--json] [--no-write] [--force] [--profile <画像路径>] [--provider kimi|deepseek]",
        "  python -m src.cli next [--topic <主题>]... [--stale-days N] [--profile <画像路径>] [--provider kimi|deepseek]",
        "  python -m src.cli done <知识点> <产出路径> [--recite <费曼复述>] [--profile <画像路径>]",
        "  python -m src.cli import <books/ 中的文件名> [--provider kimi|deepseek]",
        "  python -m src.cli align [--provider kimi|deepseek]   # 地图点对齐画像概念（T-021）",
        "  python -m src.cli explain <知识点> [--refresh] [--provider kimi|deepseek]   # 章节讲解（T-022）",
        "  python -m src.cli chat <任务时间戳> [\"问题\"]   # 终端接力：带问题单次答；不带问题进交互模式（T-032/T-034）",
        "  python -m src.cli review <任务时间戳> <代码文件> [--provider kimi|deepseek]   # 作业点评（T-028）",
        "  python -m src.cli report [--days N] [--profile <画像路径>]   # 周报复盘（T-044）",
        "  python -m src.cli serve [--port 8765] [--no-browser]   # 本地互动看板",
    ]
)
# T-032：chat 是终端接力命令（读 handoff + 调 dsh headless）
KNOWN_COMMANDS = ("sync", "import", "distill", "align", "explain", "review", "chat", "next", "done", "report", "serve")
DEFAULT_SERVE_PORT = 8765
# 提炼状态文件：记录每篇笔记的内容指纹，用于「跳过未变更」的增量提炼（T-017 I-2）
DEFAULT_STATE_NAME = ".distill-state.json"
# 经典课程实验题库（T-020）：出题时优先按画像匹配这里的条目
DEFAULT_ASSIGNMENTS_NAME = "assignments.md"
# 蒸馏稿分块大小（T-010）：单文件 67K~129K 字符，必须分块提炼。
# 30000 是实测选定值：章节基本不被硬切，7 本书总调用数 60 → 25。
DEFAULT_IMPORT_CHUNK_CHARS = 30000
# 知识点命名对齐（T-021）：每批送多少个地图点给 LLM
ALIGN_BATCH_SIZE = 150
DEFAULT_NOTES_DIR = Path("notes")
DEFAULT_BOOKS_DIR = Path("books")
DEFAULT_PROFILE_PATH = Path("profile") / "knowledge.md"
DEFAULT_TASKS_PATH = Path("profile") / "tasks.md"
# DEFAULT_SYLLABUS_PATH 来自 syllabus 模块（以前这里又定义了一份同值常量）

# 链接里可能出现的文档路径前缀 → 是否需要走 wiki 解析
_DOC_PATH_PREFIXES = ("wiki", "docx", "docs", "doc")


def parse_document_ref(raw: str) -> tuple[str, bool]:
    """把命令行输入解析为 (token, maybe_wiki)。

    - 形如 .../wiki/<token> 的链接 → maybe_wiki=True（T-001 的测试文档就是这种）
    - 形如 .../docx/<token> 的链接 → 直接是文档 ID
    - 裸 token → 直接当文档 ID
    """
    text = _strip_quotes(raw)
    if not text:
        raise ValueError("文档 ID 或链接不能为空")

    if not text.startswith("http"):
        return text, False

    path = urlparse(text).path
    parts = [p for p in path.split("/") if p]
    for index, part in enumerate(parts):
        if part in _DOC_PATH_PREFIXES and index + 1 < len(parts):
            return parts[index + 1], part == "wiki"
    raise ValueError(f"无法从链接中识别文档 ID：{text}")


def _strip_quotes(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("'"):
        text = text[1:]
    if text.endswith("'"):
        text = text[:-1]
    return text.strip()


class _UsageError(Exception):
    """命令行参数不合法：打印「原因 + 用法」并以退出码 2 结束。"""


# 带值选项缺值时的提示（各命令共用一份，避免同一个选项在不同命令里说法不一）
_OPTION_HINTS = {
    "--profile": "画像文件路径",
    "--provider": "provider 名（kimi / deepseek）",
    "--state": "状态文件路径",
    "--notes-dir": "目录",
    "--stale-days": "天数",
    "--topic": "主题名",
    "--recite": "复述内容",
    "--port": "端口号",
    "--days": "天数",
}


def _usage_error(message: str) -> int:
    print(message + "\n" + USAGE, file=sys.stderr)
    return 2


def _parse_args(
    rest: list[str],
    *,
    values: tuple[str, ...] = (),
    flags: tuple[str, ...] = (),
    repeat: tuple[str, ...] = (),
) -> tuple[dict, list[str]]:
    """把参数拆成 (选项, 位置参数)。

    - values：带一个值的选项（重复出现时最后一次生效），缺省为 None；
    - repeat：可重复的带值选项，值收集成列表；
    - flags：不带值的开关，出现即 True。
    缺值时抛 _UsageError（文案取 _OPTION_HINTS）。其余参数原样进位置参数。
    """
    options: dict = {name: None for name in values}
    options.update({name: [] for name in repeat})
    options.update({name: False for name in flags})
    positional: list[str] = []
    index = 0
    while index < len(rest):
        item = rest[index]
        if item in flags:
            options[item] = True
            index += 1
            continue
        if item in values or item in repeat:
            if index + 1 >= len(rest):
                raise _UsageError(f"{item} 后面要跟{_OPTION_HINTS.get(item, '一个值')}")
            if item in repeat:
                options[item].append(rest[index + 1])
            else:
                options[item] = rest[index + 1]
            index += 2
            continue
        positional.append(item)
        index += 1
    return options, positional


def _check_provider(provider: str | None) -> None:
    """--provider 只认已知名字（kimi / moonshot / deepseek 及别名）。"""
    if provider is not None and provider.strip().lower() not in PROVIDER_ALIASES:
        raise _UsageError(f"未知的 provider：{provider}（可选：kimi、moonshot、deepseek）")


def _profile_target(override: str | None, profile_path: Path | str | None) -> Path:
    """画像文件路径：命令行 --profile 优先，其次调用方传入，最后默认 profile/knowledge.md。"""
    if override:
        return Path(override)
    return Path(profile_path) if profile_path else DEFAULT_PROFILE_PATH


def _completer_or_report(env_path, provider: str | None, home):
    """建 LLM 客户端；配置有误时打印中文原因并返回 None（调用方退出码 1）。"""
    try:
        return make_llm_completer(env_path=env_path, provider=provider, home=home)
    except LLMError as exc:
        print(f"LLM 配置错误：{exc}", file=sys.stderr)
        return None


def make_transport() -> Transport:
    """生产传输层。测试会打桩本函数。"""
    from .feishu import RequestsTransport

    return RequestsTransport()


def make_llm_completer(
    env_path: Path | str = DEFAULT_ENV_PATH,
    provider: str | None = None,
    home: Path | str | None = None,
):
    """生产 LLM 客户端。测试会打桩本函数。

    按架构决策「Kimi 为主、DeepSeek 备用」：默认跟随 LLM_PROVIDER；
    若首选 provider 缺 Key 而另一个可用，自动降级并在 stderr 说明；都不可用才报错。
    """
    def build(name: str | None):
        return LLMClient(config_for(name, env_path=env_path, home=home))

    errors: list[tuple[str, LLMError]] = []
    try:
        return build(provider)
    except LLMError as exc:
        if provider:
            raise  # 显式指定了 provider，就不要再悄悄换别的
        errors.append((resolve_provider(None, env_path), exc))

    for candidate in ("kimi", "deepseek"):
        if any(name == candidate for name, _ in errors):
            continue
        try:
            client = build(candidate)
        except LLMError as exc:
            errors.append((candidate, exc))
            continue
        print(
            f"提示：{errors[0][0]} 不可用，自动降级到 {candidate}（备份 provider）",
            file=sys.stderr,
        )
        return client

    raise LLMError("；".join(f"{name}: {exc}" for name, exc in errors))


def _force_utf8_stdio() -> None:
    """Windows 控制台默认 GBK，中文正文会 UnicodeEncodeError；统一按 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - 已替换的流无法重配
            pass


def _run_sync(rest: list[str], env_path: Path | str, notes_dir: Path | str) -> int:
    if len(rest) != 1:
        return _usage_error("sync 需要且只需要一个参数：")

    try:
        token, maybe_wiki = parse_document_ref(rest[0])
    except ValueError as exc:
        return _usage_error(f"参数错误：{exc}")

    try:
        credentials = load_credentials(env_path=env_path)
    except CredentialError as exc:
        print(f"凭证错误：{exc}", file=sys.stderr)
        return 1

    client = FeishuClient(credentials, transport=make_transport())

    try:
        # T-009：父文档 + 全部子文档（递归）各自落盘 notes/<wiki token>.md
        result = sync_document_tree(client, token, notes_dir)
        text = client.fetch_plain_text(result.document_id)
    except FeishuApiError as exc:
        print(f"飞书接口失败（文档 {token}）：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # 兜底：只报异常类型，避免把凭证/响应体打出去
        print(f"未预期的错误（文档 {token}）：{type(exc).__name__}", file=sys.stderr)
        return 1

    print(f"已写入 {result.root}", file=sys.stderr)
    if result.children:
        print(f"子文档 {len(result.children)} 篇：", file=sys.stderr)
        for path in result.children:
            print(f"  - {path}", file=sys.stderr)
    for note in result.notes:
        print(f"提示：{note}", file=sys.stderr)
    for node_token, reason in result.skipped:
        # 无权/失败的子文档跳过并报出 ID（验收要求）
        print(f"跳过子文档 {node_token}：{reason}", file=sys.stderr)

    print(text)
    return 0


def _run_distill(
    rest: list[str],
    env_path: Path | str,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
    notes_dir: Path | str = DEFAULT_NOTES_DIR,
) -> int:
    try:
        options, positional = _parse_args(
            rest,
            values=("--state", "--notes-dir", "--profile", "--provider"),
            flags=("--json", "--no-write", "--all", "--force"),
        )
    except _UsageError as exc:
        return _usage_error(str(exc))
    as_json = options["--json"]
    write_profile = not options["--no-write"]
    force = options["--force"]
    provider = options["--provider"]
    profile_override = options["--profile"]
    notes_override = options["--notes-dir"]
    state_override = options["--state"]

    if options["--all"]:
        if positional:
            return _usage_error("--all 不能与笔记文件参数同时使用")
        return _run_distill_all(
            env_path=env_path,
            home=home,
            profile_path=profile_path,
            notes_dir=notes_override or notes_dir,
            write_profile=write_profile,
            provider=provider,
            force=force,
            state_path=state_override,
        )

    if len(positional) != 1:
        return _usage_error("distill 需要且只需要一个笔记文件参数")

    note_path = Path(positional[0])
    if not note_path.is_file():
        return _usage_error(f"找不到笔记文件：{note_path}")

    try:
        # errors="replace"：Windows 上笔记可能是 GBK，不能因为编码问题直接崩掉
        note_text = note_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"读取笔记失败：{note_path}（{type(exc).__name__}）", file=sys.stderr)
        return 1

    try:
        _check_provider(provider)
    except _UsageError as exc:
        return _usage_error(str(exc))

    completer = _completer_or_report(env_path, provider, home)
    if completer is None:
        return 1

    try:
        points = distill_note(note_text, completer=completer, source=str(note_path))
    except DistillError as exc:
        print(f"提炼失败（笔记未改动）：{exc}", file=sys.stderr)
        return 1

    if not points:
        print("本篇无可提炼的编程知识点", file=sys.stderr)
        if as_json:
            print("[]")
        return 0

    print(format_points(points), file=sys.stderr)

    if write_profile:
        target = _profile_target(profile_override, profile_path)
        try:
            # T-004：读旧画像 → 合并（同名去重、只升不降、证据追加）→ 临时文件替换
            current = KnowledgeProfile.load(target)
            write_profile_atomic(target, merge_points(current, points))
        except ProfileError as exc:
            print(f"画像写入失败（画像未改动）：{exc}", file=sys.stderr)
            return 1
        print(f"已更新画像 {target}", file=sys.stderr)

    if as_json:
        print(json.dumps([point.as_dict() for point in points], ensure_ascii=False, indent=2))
    else:
        print(format_points(points))
    return 0


def _run_distill_all(
    *,
    env_path: Path | str,
    home: Path | str | None,
    profile_path: Path | str | None,
    notes_dir: Path | str,
    write_profile: bool,
    provider: str | None,
    force: bool = False,
    state_path: Path | str | None = None,
) -> int:
    """T-016/T-017：全量提炼 notes/ 下的非空笔记。

    逐篇打印进度（I-1）；内容未变的笔记跳过、不重复调用 LLM（I-2，--force 可强制重跑）；
    单篇失败不阻塞其余，并按篇报出原因。
    """
    from .distill import (
        distill_notes,
        discover_notes,
        load_distill_state,
        save_distill_state,
    )

    notes = discover_notes(notes_dir)
    if not notes:
        print(f"notes/（{Path(notes_dir)}）里没有可提炼的非空笔记", file=sys.stderr)
        return 0

    target = Path(profile_path or DEFAULT_PROFILE_PATH)
    state_file = Path(state_path) if state_path else (target.parent / DEFAULT_STATE_NAME)
    state = load_distill_state(state_file)

    try:
        _check_provider(provider)
    except _UsageError as exc:
        return _usage_error(str(exc))

    completer = _completer_or_report(env_path, provider, home)
    if completer is None:
        return 1

    def report(position: int, total: int, name: str, status: str) -> None:
        print(f"  [{position}/{total}] {name} — {status}", file=sys.stderr, flush=True)

    batch = distill_notes(
        notes_dir,
        completer=completer,
        state=state,
        force=force,
        on_progress=report,
    )

    if write_profile and batch.succeeded:
        try:
            current = KnowledgeProfile.load(target)
            for _path, points in batch.succeeded:
                current = merge_points(current, points)
            write_profile_atomic(target, current)
        except ProfileError as exc:
            print(f"画像写入失败（画像未改动）：{exc}", file=sys.stderr)
            return 1

    if batch.succeeded:
        save_distill_state(state_file, state)

    print(batch.render(), file=sys.stderr)
    if write_profile and batch.succeeded:
        print(f"已更新画像 {target}", file=sys.stderr)

    return 0 if batch.ok else 1


def _run_next(
    rest: list[str],
    env_path: Path | str,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
    tasks_path: Path | str | None = None,
    *,
    topic_list: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> int:
    try:
        options, positional = _parse_args(
            rest, values=("--stale-days", "--profile", "--provider"), repeat=("--topic",)
        )
        if positional:
            raise _UsageError("next 不需要位置参数")
        _check_provider(options["--provider"])
        # T-035：多久没碰算"该复习了"，默认 14 天，可配
        stale_days = DEFAULT_STALE_DAYS
        if options["--stale-days"] is not None:
            try:
                stale_days = int(options["--stale-days"])
            except ValueError:
                raise _UsageError(f"--stale-days 必须是整数：{options['--stale-days']}") from None
            if stale_days < 0:
                raise _UsageError("--stale-days 不能是负数")
    except _UsageError as exc:
        return _usage_error(str(exc))
    provider = options["--provider"]
    # T-029：--topic 可重复；看板走 topic_list（已解析好的列表）
    topics: list[str] = list(topic_list or []) + options["--topic"]

    target = _profile_target(options["--profile"], profile_path)
    if not target.is_file():
        # T-017 I-3：缺前置产物统一退 1（与 done 一致），并指明下一步
        print(f"找不到画像文件：{target}：先运行 sync 同步笔记，再运行 distill --all 生成画像", file=sys.stderr)
        return 1

    try:
        profile = KnowledgeProfile.load(target)
    except ProfileError as exc:
        print(f"画像读取失败：{exc}", file=sys.stderr)
        return 1

    if len(profile.points) < MIN_POINTS:
        print(
            f"画像里只有 {len(profile.points)} 个知识点（少于 {MIN_POINTS} 个）：先多记几篇笔记再出题",
            file=sys.stderr,
        )
        return 0

    # T-010：地图现在是 markdown（多本书）；取全部书，planner 再选「与画像最相关的书」
    # T-021：若做过 align，则用「对齐后的书」选书（地图点名已换成画像概念），
    #        但返回给用户的新点仍取自**原始**地图（真名更有信息量）。
    syllabus_path = target.parent / DEFAULT_SYLLABUS_PATH.name
    raw_books = _load_syllabus(syllabus_path)
    from .alignment import apply_alignment, load_alignment

    aligned_map = load_alignment(target.parent / DEFAULT_ALIGNMENT_NAME)
    books_map = apply_alignment(raw_books, aligned_map) if (raw_books and aligned_map) else raw_books
    syllabus = books_map[0].as_dict() if books_map else None

    # T-020：题库优先。命中题库时根本不需要 LLM，所以先匹配再按需加载凭证——
    # 这样"照经典实验出题"在没配任何 LLM 凭证时也能用。
    from .assignments import assignment_to_task, load_assignments, pick_assignment
    from .planner import next_unmet_point_for_books, read_given_idents, read_recent_goals

    # T-023 L-02：读 tasks.md，避免重复出题（题库路径跳过已出条目；LLM 路径带上近期目标）
    record = Path(tasks_path) if tasks_path else (target.parent / DEFAULT_TASKS_PATH.name)
    given_idents = read_given_idents(record)
    recent_goals = read_recent_goals(record)

    assignments = load_assignments(target.parent / DEFAULT_ASSIGNMENTS_NAME)
    expected_new = (
        next_unmet_point_for_books(books_map, profile, raw_books=raw_books) if books_map else None
    )

    # 命中题库也要服从 A-06：条目的 new_skill 若与地图要求的「下一个未掌握点」不符，
    # 就换下一条；都换不到再回退 LLM（实测漏洞：原先命中即 return，绕过了这条约束）。
    task = None
    rejected: set = set()
    while assignments:
        picked = pick_assignment(assignments, profile, skip=rejected, already_given=given_idents)
        if picked is None:
            break
        candidate = assignment_to_task(picked, profile)
        if candidate.new_skill and expected_new and candidate.new_skill != expected_new:
            rejected.add(picked.ident)
            continue
        task = candidate
        break

    if task is None:
        completer = _completer_or_report(env_path, provider, home)
        if completer is None:
            return 1

        try:
            task = generate_task(
                profile,
                completer=completer,
                syllabus=syllabus,
                books=books_map,
                raw_books=raw_books,
                recent_goals=recent_goals,
                given_idents=given_idents,
                topics=topics or None,
                weaknesses=weaknesses,
                # 复习节奏要看**任务留档**：这里必须给真实路径，
                # 传 None 的话复习分支永远不会触发（真机实测：连出 4 题全是新题）
                tasks_path=record,
                stale_days=stale_days,
            )
        except PlannerError as exc:
            print(f"出题失败：{exc}", file=sys.stderr)
            return 1

    # T-035 语义修正（真机实测后）：**出题本身不算"碰到了"**。
    # 起初按"任务用到了这个点"刷新 last_touched，结果 LLM 每次把全部已掌握点都写进 skills，
    # 于是每出一次题所有点都被刷成今天 —— 复习队列永远挑不出超期点（实测第 4 题仍出新题）。
    # 真正算"复习了/学习了"的只有 done 回写与 distill 学到；复习题完成后走 done 即可。
    try:
        append_task_record(record, task)
    except PlannerError as exc:
        print(f"任务已生成但留档失败：{exc}", file=sys.stderr)
    else:
        print(f"已留档 {record}", file=sys.stderr)

    print(render_task(task))
    return 0


def _run_import(
    rest: list[str],
    env_path: Path | str,
    home: Path | str | None = None,
    books_dir: Path | str | None = None,
    syllabus_path: Path | str | None = None,
) -> int:
    try:
        options, positional = _parse_args(rest, values=("--provider",))
        if len(positional) != 1:
            raise _UsageError("import 需要且只需要一个书名文件名参数")
        _check_provider(options["--provider"])
    except _UsageError as exc:
        return _usage_error(str(exc))

    books = Path(books_dir or DEFAULT_BOOKS_DIR)
    source = Path(positional[0])
    if not source.is_absolute():
        source = books / source
    if not source.is_file():
        return _usage_error(f"找不到蒸馏稿：{source}（请把蒸馏稿放进 {books}）")

    completer = _completer_or_report(env_path, options["--provider"], home)
    if completer is None:
        return 1

    # T-010：长稿分块提炼——逐块打印进度，避免几百秒黑屏（与 distill 一致的手感）
    def report(index: int, total: int) -> None:
        print(f"  正在提炼第 {index}/{total} 块…", file=sys.stderr, flush=True)

    approx = source.stat().st_size
    print(
        f"蒸馏稿 {source.name}（约 {approx // 1024} KB）："
        f"按 {DEFAULT_IMPORT_CHUNK_CHARS} 字符分块提炼（长稿不会整本塞进一次调用）",
        file=sys.stderr,
    )

    try:
        book, target = import_book(
            source,
            completer=completer,
            syllabus_path=syllabus_path or DEFAULT_SYLLABUS_PATH,
            max_chars=DEFAULT_IMPORT_CHUNK_CHARS,
            on_progress=report,
        )
    except SyllabusError as exc:
        print(f"导入失败（知识地图未改动）：{exc}", file=sys.stderr)
        return 1

    points = sum(len(chapter.points) for chapter in book.chapters)
    print(
        f"《{book.book}》：{len(book.chapters)} 章、{points} 个知识点",
        file=sys.stderr,
    )
    print(f"已更新知识地图 {target}", file=sys.stderr)
    # T-023：导入后明确提示下一步——地图点名与画像概念通常对不上，不跑 align 出题会不准
    print(
        "提示：地图里的知识点名与画像里的概念名往往不一致，"
        "建议接着运行 align 做一次命名对齐（出题与讲解才会贴着画像走）",
        file=sys.stderr,
    )
    return 0


def _build_board(
    env_path: Path | str,
    notes_dir: Path | str,
    profile_path: Path | str | None,
    tasks_path: Path | str | None,
    home: Path | str | None,
):
    """把看板的固定动作接到真实命令上（T-013）。

    只挂这四个固定动作 + 改状态；不暴露任何"自由命令"入口。
    """
    from .dashboard import TaskBoard

    target = Path(profile_path or DEFAULT_PROFILE_PATH)
    record = Path(tasks_path) if tasks_path else (target.parent / DEFAULT_TASKS_PATH.name)

    def capture(runner) -> str:
        """跑一个真实命令，返回可展示的文本。

        命令的 stderr（逐篇成败汇总等）也一并捕获：看板要把结果给人看，不能只报"退出码 1"。
        """
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            code = runner()
        text = "\n".join(part.strip() for part in (out_buf.getvalue(), err_buf.getvalue()) if part.strip())
        if code != 0:
            raise RuntimeError(f"退出码 {code}" + (f"\n{text}" if text else ""))
        return text or "完成"

    def _sync_step() -> tuple[str, str]:
        """跑同步那一步，返回 (输出文本, 备注)。T-023 L-05 的 ROOT_DOC 逻辑原样保留。"""
        root = _read_env_value(env_path, "FEISHU_ROOT_DOC")
        if root:
            output = capture(lambda: _run_sync([root], env_path, notes_dir))
            return output, f"（已按 FEISHU_ROOT_DOC 同步整棵树：{root}）"

        candidates = sorted(Path(notes_dir).glob("*.md")) if Path(notes_dir).is_dir() else []
        if not candidates:
            raise RuntimeError(
                "还没有本地笔记：先在命令行运行 sync <wiki链接>，"
                "或在 .env 里配置 FEISHU_ROOT_DOC 让本按钮同步整棵树"
            )
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        output = capture(lambda: _run_sync([newest.stem], env_path, notes_dir))
        return (
            output,
            "（本按钮只同步了最近一篇；把学习库根节点填进 .env 的 FEISHU_ROOT_DOC，"
            "以后点一次就同步整棵树）",
        )

    def op_sync() -> str:
        """T-025：同步 + **增量提炼**。

        客户两次踩坑"点了同步、画像却没变"——因为 sync 只落盘笔记。
        这里接上 distill --all（sha256 跳过未变更的篇），结果分两段展示。
        命令行 sync 仍是单职责，只有看板这个按钮做联动。
        """
        synced, note = _sync_step()
        lines = ["【同步】", synced, note, "", "【提炼】"]

        try:
            distilled = capture(
                lambda: _run_distill(
                    ["--all"], env_path, home=home, profile_path=target, notes_dir=notes_dir
                )
            )
            lines.append(distilled)
        except Exception as exc:
            # 提炼失败不阻塞：同步已经生效，如实报出来让用户能重试
            lines.append(f"提炼失败：{exc}")
        return "\n".join(lines)

    def op_distill() -> str:
        # T-016：全量提炼（原先只挑 mtime 最新的一篇），逐篇成败都回报给看板
        from .distill import discover_notes

        if not discover_notes(notes_dir):
            raise RuntimeError("还没有可提炼的笔记：先同步或放入笔记")
        return capture(
            lambda: _run_distill(
                ["--all"],
                env_path,
                home=home,
                profile_path=target,
                notes_dir=notes_dir,
            )
        )

    def op_next() -> str:
        # T-035：把错题本与"多久算超期"一起带下去（看板与 CLI 走同一条路）
        from .weaknesses import weaknesses_text

        complaints = weaknesses_text(target.parent)
        return capture(
            lambda topics=None: _run_next(
                [],
                env_path,
                home=home,
                profile_path=target,
                tasks_path=record,
                topic_list=topics,
                weaknesses=complaints,
            )
        )

    def op_done(name: str, path: str, recite: str = "") -> str:
        # T-024 M-01：看板回写表单补齐了 name/path/recite 三个入参。
        # T-035 的「做掉就从错题本移除」由 _run_done 负责（CLI 与看板同一条路径，
        # 以前这里又手写了一遍同样的移除逻辑——_run_done 已经移完，那一遍永远是空操作）。
        args = [str(name), str(path)]
        if str(recite or "").strip():
            args += ["--recite", str(recite).strip()]
        return capture(lambda: _run_done(args, profile_path=target))

    def _terminal_launcher():
        """弹终端用的发射器（单独抽出来便于测试打桩）。"""
        from .terminal import launch_chat_terminal

        return launch_chat_terminal

    def op_chat(task: str, message: str) -> str:
        """T-034：面板里的一轮对话。

        每轮重新拼 prompt（handoff 全文 + 该任务历史 + 新消息），
        调 dsh headless 拿回答，**问答都写进该任务的留档**。
        """
        from .chat import ChatError, chat_once, find_dsh, read_handoff
        from .chat_session import (
            ChatSessionError,
            append_turn,
            build_prompt,
            build_summarizer,
            load_turns,
        )

        try:
            context = read_handoff(target.parent, task)
        except ChatError as exc:
            raise RuntimeError(str(exc)) from None

        # T-043：历史超长时把最旧轮次压成摘要（走真 LLM），摘要落盘缓存
        try:
            summarizer = build_summarizer(
                make_llm_completer(env_path=env_path, home=home)
            )
        except Exception:
            summarizer = None  # 拿不到 LLM 时退回硬裁，不影响本轮

        try:
            turns = load_turns(target.parent, task)
            prompt = build_prompt(
                context,
                turns,
                message,
                summarizer=summarizer,
                profile_dir=target.parent,
                when=task,
            )
        except ChatSessionError as exc:
            raise RuntimeError(str(exc)) from None

        executable = find_dsh()
        if not executable:
            raise RuntimeError(
                "找不到 dsh 命令：先安装 DeepSeek Harness（npm i -g @deepseek-ai/dsh）再试。"
            )

        try:
            answer = chat_once(executable, prompt)
        except ChatError as exc:
            raise RuntimeError(str(exc)) from None

        try:
            append_turn(target.parent, task, role="user", text=message)
            append_turn(
                target.parent,
                task,
                role="assistant",
                text=answer.strip(),
                # T-037：思考流单独存，别混进答案
                thinking=getattr(answer, "thinking", ""),
            )
        except ChatSessionError as exc:
            raise RuntimeError(f"写对话留档失败：{exc}") from None

        return answer.strip()

    def op_handoff(task: str) -> str:
        """T-031：把这道题的上下文交给 DSH 接力。

        直通（自动建会话）在本机**不可用**——已实测：DSH 桌面版确实有
        POST /api/session/create，但需要 19387 同源的会话 cookie；桌面版启动令牌
        只在 IPC 里上报、不留磁盘副本，外部进程拿不到，跨源 fetch 也被 CORS 挡。
        所以这里走**降级**：生成上下文文件 + 给出可直接粘贴的提问，
        并如实说明为什么不自动开。
        """
        from .handoff import HandoffError, build_questions, write_handoff
        from .planner import read_task_records
        from .syllabus import load_syllabus

        entry = next((r for r in read_task_records(record) if r.when == task), None)
        if entry is None:
            raise RuntimeError(f"任务记录里没有时间戳为「{task}」的块")

        # 提交过作业就带上那份代码（取最后一次提交）
        code = ""
        for review in reversed(getattr(entry, "reviews", []) or []):
            if getattr(review, "code", ""):
                code = review.code
                break

        syllabus_file = target.parent / DEFAULT_SYLLABUS_PATH.name
        try:
            profile = KnowledgeProfile.load(target)
        except Exception:
            profile = None
        try:
            books = load_syllabus(syllabus_file) if syllabus_file.is_file() else []
        except Exception:
            books = []
        # T-047：和 next 同口径——先 apply_alignment 再查出处。地图里存的是书上的
        # 原话（「id 做页面内锚点」），任务卡记的是画像概念名（「超链接 a 标签
        # （href/target）」）；不做这一步，第 4 段会整段找不到——实测这道 nav 题的
        # 4 个知识点全部落到 None。
        try:
            from .alignment import apply_alignment, load_alignment, merge_aligned_names

            aligned_map = load_alignment(target.parent / DEFAULT_ALIGNMENT_NAME)
            if books and aligned_map:
                # 两套名字都留着查：任务卡记的是画像概念名（「超链接 a 标签（href/target）」），
                # 也有人直接照书抄地图原名（「id 做页面内锚点」）——merge 后两种都能命中。
                books = merge_aligned_names(books, apply_alignment(books, aligned_map))
        except Exception:
            pass  # 对齐失败就退回原始地图，不能因此让接力文件生成不出来

        try:
            path = write_handoff(
                target.parent,
                record=entry,
                code=code,
                profile=profile,
                books=books,
            )
        except HandoffError as exc:
            raise RuntimeError(f"生成接力上下文失败：{exc}") from None

        # 显示的路径要**能直接照抄**：优先"相对当前工作目录"（用户就在这里），
        # 拿不到才退回绝对路径。曾经按 target.parent.parent 算，结果把 profile/ 前缀吃掉了。
        try:
            shown = Path(os.path.relpath(path, Path.cwd()))
        except ValueError:
            shown = path
        questions = build_questions(entry, profile)
        # T-033：顺手弹一个终端窗口（非 Windows / 失败都静默降级，不影响结果）
        # T-049：默认**不弹**——入口已收敛到插件面板；DSH_TERMINAL_POPUP=1 才恢复
        from .dashboard import terminal_popup_enabled

        launched = False
        try:
            from .terminal import FIRST_QUESTIONS, current_python

            launched = bool(
                terminal_popup_enabled()
                and _terminal_launcher()(
                    current_python(),
                    entry.when,
                    FIRST_QUESTIONS[0],
                    profile_path=str(target),
                )
            )
        except Exception:
            launched = False

        lines = [
            f"已生成接力上下文：{shown}",
            "",
            "该文件包含：任务卡 / 本次提交的代码 / 画像相关点 / 书籍出处与章节 / 提问引导。",
            "",
            "**主入口（推荐）**：卡片下方已出现「展开聊天面板」——点开后首条引导提问会自动发出，",
            "之后在面板里直接打字追问即可；回答渲染回面板，不刷新页面、不跳滚动。",
            "对话按任务隔离，留档到同名 .chat.md。",
            "",
        ]
        if launched:
            lines.extend(
                [
                    "【次级入口】另弹了一个终端窗口跑 chat（T-033 保留的备选路径）；",
                    "不想用终端就忽略它，直接在卡片下面的聊天面板里问更顺手。",
                ]
            )
        else:
            lines.extend(
                [
                    "【没弹终端】非 Windows 或当前环境不允许弹窗——不影响，照下面手动方式走，或用聊天面板。",
                ]
            )
        lines.extend(
            [
                "（说明：这两种方式走的都是本机 dsh headless，不是直连 DSH 会话——直连需要 19387 同源的会话",
                "  cookie 才能建立；桌面版令牌不留磁盘副本、跨源也被 CORS 挡，所以这里不绕过鉴权。）",
                "",
                "【手动方式】不想用面板就手动粘贴——把下面任一句（或整个上下文文件）贴进 DSH 对话框：",
            ]
        )
        for index, question in enumerate(questions, start=1):
            lines.append(f"  {index}. {question}")
        lines.extend(
            [
                "",
                "【不想开图形界面】命令行一次性问也行：",
                f'  dsh --profile headless "读 {shown}，回答其中的提问"',
            ]
        )
        return "\n".join(lines)

    def op_review(task: str, code: str) -> str:
        # T-028：按验收方式点评，并把「提交时间 + 评价 + 建议」留档到对应任务块；
        # T-035：问题点并进错题本——与 CLI review 走同一个 _review_and_record
        # （以前看板这条路径漏了错题本，只有命令行 review 会记）。
        from .planner import PlannerError
        from .review import ReviewError

        # 先确认任务存在再建 LLM 客户端：时间戳写错时报「没有这个任务」，而不是先报 LLM 配置问题
        if _find_task(record, task) is None:
            raise RuntimeError(f"任务记录里没有时间戳为「{task}」的块")
        try:
            completer = make_llm_completer(env_path=env_path, home=home)
            return _review_and_record(record, task, code, completer).render()
        except (ReviewError, PlannerError, LLMError) as exc:
            raise RuntimeError(str(exc)) from None

    def op_delete_task(when: str) -> str:
        # T-027：按时间戳删掉一个任务块（只动目标块，临时文件 + 替换）
        from .planner import PlannerError, delete_task_record

        try:
            delete_task_record(record, when)
        except PlannerError as exc:
            raise RuntimeError(str(exc)) from None
        return f"已删除任务 {when}"

    def op_explain(name: str) -> str:
        # T-022：看板「讲解」按钮 → 同一个 explain 命令（notes_dir 可能是 str，统一转 Path）
        books_dir = Path(notes_dir).parent / DEFAULT_BOOKS_DIR.name
        return capture(
            lambda: _run_explain([str(name)], env_path, home=home, profile_path=target, books_dir=books_dir)
        )

    return TaskBoard(
        target.parent,
        operations={  # 固定动作集：键必须与 dashboard.FIXED_ACTIONS 一一对应
            "sync": op_sync,
            "distill": op_distill,
            "next": op_next,
            "done": op_done,
            "explain": op_explain,
            "delete_task": op_delete_task,
            "review": op_review,
            "handoff": op_handoff,
            "chat": op_chat,
        },
    )


def _run_serve(
    rest: list[str],
    profile_path: Path | str | None = None,
    env_path: Path | str = DEFAULT_ENV_PATH,
    notes_dir: Path | str = DEFAULT_NOTES_DIR,
    tasks_path: Path | str | None = None,
    home: Path | str | None = None,
) -> int:
    from .dashboard import build_server

    try:
        options, positional = _parse_args(rest, values=("--port",), flags=("--no-browser",))
        if positional:
            raise _UsageError("serve 不需要位置参数")
        port = DEFAULT_SERVE_PORT
        port_text = options["--port"]
        if port_text is not None:
            try:
                port = int(port_text)
            except ValueError:
                raise _UsageError(f"端口必须是数字：{port_text}") from None
            if not (0 <= port <= 65535):
                raise _UsageError(f"端口超出范围：{port}")
    except _UsageError as exc:
        return _usage_error(str(exc))
    open_browser = not options["--no-browser"]

    target = Path(profile_path or DEFAULT_PROFILE_PATH)
    profile_dir = target.parent if target.name.endswith(".md") else target

    board = _build_board(env_path, notes_dir, profile_path, tasks_path, home)

    try:
        server = build_server(profile_dir, port=port, board=board)
    except OSError as exc:
        # T-024 M-05：端口被占用/无权限时给中文提示（含原因与换端口建议），不抛 traceback
        reason = getattr(exc, "strerror", "") or type(exc).__name__
        print(
            f"启动失败：端口 {port} 无法监听（{reason}）。"
            f"换一个端口重试：python -m src.cli serve --port {port + 1}",
            file=sys.stderr,
        )
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"本地只读看板已启动：{url}", file=sys.stderr)
    print(f"数据目录：{profile_dir}（只读，不会改动任何文件）", file=sys.stderr)
    print("按 Ctrl+C 停止", file=sys.stderr)

    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止", file=sys.stderr)
    except OSError as exc:
        # T-024 M-05：端口被占用（或权限不足）时给中文提示，别抛 traceback
        print(
            f"启动失败：端口 {port} 无法监听（{exc.strerror or type(exc).__name__}）。"
            f"可能是已被占用，换一个端口重试：python -m src.cli serve --port {port + 1}",
            file=sys.stderr,
        )
        return 1
    finally:
        server.server_close()
    return 0


def _run_done(
    rest: list[str],
    profile_path: Path | str | None = None,
) -> int:
    try:
        # T-019：--recite 是费曼复述。带了它就把状态升到「输出」。
        options, positional = _parse_args(rest, values=("--profile", "--recite"))
        if len(positional) != 2:
            raise _UsageError("done 需要两个参数：<知识点> <产出路径>")
    except _UsageError as exc:
        return _usage_error(str(exc))
    recite = options["--recite"] or ""

    name, product = positional
    target = _profile_target(options["--profile"], profile_path)
    if not target.is_file():
        print(f"找不到画像文件：{target}：先运行 sync + distill", file=sys.stderr)
        return 1

    try:
        updated = mark_done(KnowledgeProfile.load(target), name, product, recite=recite)
        # 用户可能只写缩略名「列表」，画像里却是「列表（ul/ol/li）」：后面刷时间戳、
        # 清错题本都要用**解析后的完整点名**（mark_done 已经按同一规则解析过歧义/缩略名），
        # 只用缩略名做精确匹配的话永远对不上（实测踩过两次）。
        full_name = resolve_point_name(updated, name)
        # T-035：回写也算"碰过"这个知识点，刷新 last_touched（复习队列靠它）
        updated = touch_points(updated, [normalize_point_name(name), full_name or ""])
        write_profile_atomic(target, updated)
    except ProfileError as exc:
        print(f"回写失败（画像未改动）：{exc}", file=sys.stderr)
        return 1

    # T-035：done 涉及的知识点相关薄弱点要从错题本移除（CLI 与看板共用这一处）
    removed = _forget_weaknesses(target.parent, {normalize_point_name(name), str(name).strip(), full_name or ""})
    if removed:
        print("（已从错题本移除：" + "、".join(removed) + "）", file=sys.stderr)

    point = updated.find(full_name or normalize_point_name(name))
    shown, evidence = (point.name, point.evidence) if point else (str(name).strip(), "")
    if recite:
        print(f"已把「{shown}」升为「输出」（含费曼复述），证据：{evidence}", file=sys.stderr)
    else:
        print(f"已把「{shown}」标记为「做过」，证据：{evidence}", file=sys.stderr)
    print(f"已更新画像 {target}", file=sys.stderr)
    return 0


def _forget_weaknesses(profile_dir: Path, names: set[str]) -> list[str]:
    """把文本里提到这些知识点的薄弱点从错题本移除，返回移除的条目。

    错题本坏了不该挡住回写：任何异常都只当"什么也没移除"。
    """
    from .weaknesses import load_weaknesses, remove_weaknesses

    wanted = {name for name in names if name}
    try:
        hit = [item.text for item in load_weaknesses(profile_dir) if any(word in item.text for word in wanted)]
        return remove_weaknesses(profile_dir, hit) if hit else []
    except Exception:
        return []


def _run_report(
    rest: list[str],
    *,
    profile_path: Path | str | None = None,
    repo_root: Path | str | None = None,
) -> int:
    """T-044：周报复盘——把窗口内的学习活动汇总成 markdown。"""
    from .report import DEFAULT_DAYS, build_report

    try:
        options, positional = _parse_args(rest, values=("--days", "--profile"))
        if positional:
            raise _UsageError(f"report 不认识参数：{positional[0]}")
        days = DEFAULT_DAYS
        if options["--days"] is not None:
            try:
                days = int(options["--days"])
            except ValueError:
                raise _UsageError(f"--days 必须是整数（收到 {options['--days']}）") from None
            if days < 1:
                raise _UsageError("--days 必须 >= 1")
    except _UsageError as exc:
        return _usage_error(str(exc))

    target = _profile_target(options["--profile"], profile_path)
    if not target.is_file():
        print(f"找不到画像文件：{target}：先运行 sync + distill", file=sys.stderr)
        return 1

    root = Path(repo_root) if repo_root else target.parent.parent
    print(build_report(target.parent, days=days, repo_root=root), end="")
    return 0


def _run_chat(
    rest: list[str],
    env_path: Path | str = DEFAULT_ENV_PATH,
    *,
    profile_path: Path | str | None = None,
    home: Path | str | None = None,
) -> int:
    """T-032：chat <任务时间戳> "问题" —— 终端接力，把答案透传到 stdout。

    走 subprocess 列表参数调 `dsh --profile headless`，**不经过 shell**。
    """
    from .chat import ChatError, assemble_prompt, chat_once, find_dsh, read_handoff

    try:
        # --profile：和别的子命令一致，允许把画像路径当"项目根"用（handoff 就在它旁边）
        options, positional = _parse_args(rest, values=("--profile",))
        unsupported = next((item for item in positional if item in ("--provider", "--port")), None)
        if unsupported:
            # 这两个对 chat 没意义，提前报错免得被当成问题的一部分
            raise _UsageError(f"chat 不支持 {unsupported}")
        # T-034：不带问题 → 进交互模式（REPL）；带问题 → 保持 T-032 单次模式
        if len(positional) not in (1, 2):
            raise _UsageError('chat 需要一个或两个参数：<任务时间戳> ["问题"]')
    except _UsageError as exc:
        return _usage_error(str(exc))

    when = positional[0]
    question = positional[1] if len(positional) == 2 else None
    target = _profile_target(options["--profile"], profile_path)

    if question is None:
        # 交互模式：每轮把 handoff + 该任务历史 + 新消息拼成 prompt
        from .chat_session import (
            ChatSessionError,
            append_turn,
            build_prompt,
            build_summarizer,
            load_turns,
        )
        from .repl import run_repl

        # T-043：REPL 也一样——超长历史压成摘要并落盘缓存。
        # （以前 _run_chat 没有 home 参数，这里的 home 是未定义名字：NameError 被下面的
        #  except 吞掉，REPL 的摘要器从来没建成过，超长历史一律被硬裁。）
        try:
            repl_summarizer = build_summarizer(
                make_llm_completer(env_path=env_path, home=home)
            )
        except Exception:
            repl_summarizer = None

        try:
            context = read_handoff(target.parent, when)
        except ChatError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        executable = find_dsh()
        if not executable:
            print(
                "找不到 dsh 命令：请先安装 DeepSeek Harness（npm i -g @deepseek-ai/dsh）。",
                file=sys.stderr,
            )
            return 1

        def ask(message: str) -> str:
            turns = load_turns(target.parent, when)
            prompt = build_prompt(
                context,
                turns,
                message,
                summarizer=repl_summarizer,
                profile_dir=target.parent,
                when=when,
            )
            answer = chat_once(executable, prompt)
            append_turn(target.parent, when, role="user", text=message)
            append_turn(
                target.parent,
                when,
                role="assistant",
                text=answer.strip(),
                thinking=getattr(answer, "thinking", ""),
            )
            return answer.strip()

        # T-036：弹窗进这个循环时，启动就先自动问一条（用户打开窗口就能看到回答），
        # 之后停在「你：」提示符等追问。
        from .terminal import FIRST_QUESTIONS

        return run_repl(ask=ask, initial=FIRST_QUESTIONS[0])

    try:
        context = read_handoff(target.parent, when)
        prompt = assemble_prompt(context, question)
    except ChatError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    executable = find_dsh()
    if not executable:
        print(
            "找不到 dsh 命令：请先安装 DeepSeek Harness（npm i -g @deepseek-ai/dsh），"
            "确认 dsh 在 PATH 里再试。\n"
            "（也可以直接照抄接力文件里的提问，手动贴进 DSH。）",
            file=sys.stderr,
        )
        return 1

    # 如实提醒：headless profile 若被人设覆盖，答案质量会受影响（实测过）
    from .chat import headless_persona_override

    patch = headless_persona_override()
    if patch:
        print(
            f"提醒：headless profile 配了人设覆盖（{patch}），"
            "它的 system prompt 会压过这份接力上下文——实测里它常会先自我介绍、"
            "并要求你再贴一次材料，答案可能跑偏。\n"
            "    想要靠谱的答案：在看板的接力文件里复制提问，直接在 DSH 会话里问；"
            "或把该 profile 的 personaPrefix 去掉。",
            file=sys.stderr,
        )

    try:
        answer = chat_once(executable, prompt)
    except ChatError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    # T-034：单次模式也写进留档，保证"留档完整"
    try:
        from .chat_session import append_turn

        append_turn(target.parent, when, role="user", text=question)
        append_turn(
            target.parent,
            when,
            role="assistant",
            text=answer.strip(),
            thinking=getattr(answer, "thinking", ""),
        )
    except Exception:
        pass  # 留档失败不影响这次回答

    print(answer.rstrip())
    return 0


def _run_review(
    rest: list[str],
    env_path: Path | str = DEFAULT_ENV_PATH,
    *,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
    tasks_path: Path | str | None = None,
) -> int:
    """T-028：review <任务时间戳> <代码文件> —— 按验收方式点评并留档。"""
    from .planner import PlannerError
    from .review import MAX_CODE_CHARS, ReviewError

    try:
        options, positional = _parse_args(rest, values=("--provider",))
        if len(positional) != 2:
            raise _UsageError("review 需要两个参数：<任务时间戳> <代码文件>")
        _check_provider(options["--provider"])
    except _UsageError as exc:
        return _usage_error(str(exc))

    when, code_source = positional
    target = _profile_target(None, profile_path)
    tasks = Path(tasks_path) if tasks_path else (target.parent / DEFAULT_TASKS_PATH.name)

    # 代码可以给文件路径；给了不存在的文件要明确报错，而不是当成代码内容
    code_path = Path(code_source)
    looks_like_path = code_path.suffix != "" and len(code_source) < 260
    if looks_like_path:
        if not code_path.is_file():
            print(f"找不到代码文件：{code_path}", file=sys.stderr)
            return 1
        try:
            code = code_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"读取代码文件失败：{code_path}（{type(exc).__name__}）", file=sys.stderr)
            return 1
    else:
        code = code_source

    if _find_task(tasks, when) is None:
        print(f"任务记录里没有时间戳为「{when}」的块：{tasks}", file=sys.stderr)
        return 1

    try:
        completer = make_llm_completer(provider=options["--provider"], env_path=env_path, home=home)
        result = _review_and_record(tasks, when, code, completer)
    except (ReviewError, LLMError) as exc:
        print(f"点评失败（未留档）：{exc}", file=sys.stderr)
        return 1
    except PlannerError as exc:
        print(f"留档失败（任务记录未改动）：{exc}", file=sys.stderr)
        return 1

    print(result.render())
    if result.truncated:
        print(f"（代码超过 {MAX_CODE_CHARS} 字符，已截断后点评）", file=sys.stderr)
    print(f"已留档到 {tasks}（任务 {when}）", file=sys.stderr)
    return 0


def _find_task(tasks_path: Path | str, when: str):
    """按时间戳找任务记录（找不到返回 None）。"""
    from .planner import read_task_records

    return next((record for record in read_task_records(tasks_path) if record.when == when), None)


def _review_and_record(tasks_path: Path, when: str, code: str, completer):
    """点评 + 留档 + 并进错题本：CLI review 与看板「提交作业」共用这一条路径。

    - 找不到任务块 → PlannerError；LLM 失败 → ReviewError（都还没写任何文件）；
    - 留档失败 → PlannerError（任务记录未改动）；
    - 错题本写失败不影响点评结果（点评不能白做）。
    """
    from .planner import PlannerError, append_review
    from .review import review_code

    entry = _find_task(tasks_path, when)
    if entry is None:
        raise PlannerError(f"任务记录里没有时间戳为「{when}」的块")
    result = review_code(goal=entry.goal, acceptance=entry.acceptance, code=code, completer=completer)
    append_review(
        tasks_path,
        when,
        code=result.code,
        feedback=result.feedback,
        suggestion=result.suggestion,
        truncated=result.truncated,
    )
    # T-035：把这次点评抽出的「问题点」并进错题本（最多 3 条，去重）
    if result.problems:
        try:
            from .weaknesses import merge_weaknesses

            merge_weaknesses(Path(tasks_path).parent, result.problems)
        except Exception:
            pass  # 错题本写失败不该让点评白做
    return result


def _run_explain(
    rest: list[str],
    env_path: Path | str,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
    books_dir: Path | str | None = None,
) -> int:
    """T-022：讲解一个知识点（地图定位 → 取参考文本 → LLM 讲解）。"""
    from .explain import DEFAULT_SRC_DIR, ExplainError, default_cache_dir, explain_point

    try:
        options, positional = _parse_args(rest, values=("--provider",), flags=("--refresh",))
        if len(positional) != 1:
            raise _UsageError("explain 需要且只需要一个知识点参数")
        _check_provider(options["--provider"])
    except _UsageError as exc:
        return _usage_error(str(exc))

    target = Path(profile_path or DEFAULT_PROFILE_PATH)
    books_map = _load_syllabus(target.parent / DEFAULT_SYLLABUS_PATH.name)
    if not books_map:
        print(
            f"还没有知识地图：先运行 import 导入蒸馏稿（{target.parent / DEFAULT_SYLLABUS_PATH.name}）",
            file=sys.stderr,
        )
        return 1

    completer = _completer_or_report(env_path, options["--provider"], home)
    if completer is None:
        return 1

    profile = KnowledgeProfile.load(target) if target.is_file() else None
    try:
        result = explain_point(
            positional[0],
            books_map,
            completer=completer,
            books_dir=books_dir or DEFAULT_BOOKS_DIR,
            src_dir=DEFAULT_SRC_DIR,
            profile=profile,
            alignment_path=target.parent / DEFAULT_ALIGNMENT_NAME,
            cache_dir=default_cache_dir(target.parent),
            refresh=options["--refresh"],
        )
    except ExplainError as exc:
        print(f"讲解失败：{exc}", file=sys.stderr)
        return 1

    print(result.render())
    return 0



def _read_env_value(env_path: Path | str, key: str) -> str:
    """从 .env 里读一个可选配置项（不涉及凭证，读不到就返回空串）。

    与凭证读取共用 credentials.parse_env_file 的解析规则（以前这里手写了第三份 .env 解析）。
    """
    return str(read_env_values(env_path).get(key, "")).strip()


def _run_align(
    rest: list[str],
    env_path: Path | str,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
) -> int:
    """T-021：把知识地图里的细粒度点名对齐到画像的既有概念，结果落盘 alignment.json。"""
    try:
        options, positional = _parse_args(rest, values=("--provider",))
        if positional:
            raise _UsageError("align 不接受位置参数")
        _check_provider(options["--provider"])
    except _UsageError as exc:
        return _usage_error(str(exc))

    from .alignment import align_points, save_alignment, summary

    target = Path(profile_path or DEFAULT_PROFILE_PATH)
    if not target.is_file():
        print(f"找不到画像文件：{target}：先运行 sync + distill 生成画像", file=sys.stderr)
        return 1
    books = _load_syllabus(target.parent / DEFAULT_SYLLABUS_PATH.name)
    if not books:
        print(
            f"还没有知识地图：先运行 import 导入蒸馏稿（{target.parent / DEFAULT_SYLLABUS_PATH.name}）",
            file=sys.stderr,
        )
        return 1

    try:
        profile = KnowledgeProfile.load(target)
    except ProfileError as exc:
        print(f"画像读取失败：{exc}", file=sys.stderr)
        return 1

    points: list[str] = []
    for book in books:
        for chapter in book.chapters:
            for point in chapter.points:
                name = str(point).strip()
                if name and name not in points:
                    points.append(name)
    if not points:
        print("知识地图里没有知识点，无需对齐", file=sys.stderr)
        return 0

    completer = _completer_or_report(env_path, options["--provider"], home)
    if completer is None:
        return 1

    print(
        f"知识地图 {len(books)} 本书、{len(points)} 个点；画像 {len(profile.points)} 个概念。"
        f"按每批 {ALIGN_BATCH_SIZE} 个点用 LLM 对齐…",
        file=sys.stderr,
    )
    try:
        aligned = align_points(points, profile, completer=completer, batch_size=ALIGN_BATCH_SIZE)
    except AlignmentError as exc:
        print(f"对齐失败（对齐结果未改动）：{exc}", file=sys.stderr)
        return 1

    destination = target.parent / DEFAULT_ALIGNMENT_NAME
    try:
        save_alignment(destination, aligned)
    except AlignmentError as exc:
        print(f"对齐结果落盘失败：{exc}", file=sys.stderr)
        return 1

    stats = summary(aligned)
    print(
        f"已对齐 {stats['mapped']}/{stats['total']} 个点（{stats['ratio'] * 100:.0f}%），"
        f"其余 {stats['new']} 个是画像里还没有的新概念",
        file=sys.stderr,
    )
    print(f"已写入 {destination}", file=sys.stderr)
    return 0


def _load_syllabus(path: Path):
    """读取知识地图，返回 **BookMap 列表**（T-010 定稿：markdown 格式）。

    实测 bug：旧实现用 json.loads 读 markdown 地图，永远返回 None，
    导致 A-06「新点来自地图按书序的下一个未掌握点」从未真正生效。

    现在返回全部书，交给 planner 按「与画像最相关的书」选点（见 next_unmet_point_for_books）。
    文件不存在或没有可解析的书 → None（按「无地图」处理）。
    """
    from .syllabus import load_syllabus

    target = Path(path)
    if not target.is_file():
        return None
    try:
        books = load_syllabus(target)
    except Exception:
        return None
    return books or None


def main(
    argv: list[str] | None = None,
    env_path: Path | str = DEFAULT_ENV_PATH,
    notes_dir: Path | str = DEFAULT_NOTES_DIR,
    home: Path | str | None = None,
    profile_path: Path | str | None = None,
    tasks_path: Path | str | None = None,
    books_dir: Path | str | None = None,
    syllabus_path: Path | str | None = None,
) -> int:
    _force_utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        print(USAGE, file=sys.stderr)
        return 2

    if args[0] in {"-h", "--help"}:
        print(USAGE, file=sys.stderr)
        return 0

    command, rest = args[0], args[1:]

    def run_next() -> int:
        # T-035：CLI 与看板走同一条路——都带上错题本
        from .weaknesses import weaknesses_text

        try:
            complaints = weaknesses_text(_profile_target(None, profile_path).parent)
        except Exception:
            complaints = []
        return _run_next(
            rest, env_path, home=home, profile_path=profile_path, tasks_path=tasks_path, weaknesses=complaints
        )

    handlers = {
        "sync": lambda: _run_sync(rest, env_path, notes_dir),
        "distill": lambda: _run_distill(rest, env_path, home=home, profile_path=profile_path, notes_dir=notes_dir),
        "next": run_next,
        "done": lambda: _run_done(rest, profile_path=profile_path),
        "report": lambda: _run_report(rest, profile_path=profile_path),
        "serve": lambda: _run_serve(
            rest, profile_path=profile_path, env_path=env_path, notes_dir=notes_dir, tasks_path=tasks_path, home=home
        ),
        "import": lambda: _run_import(rest, env_path, home=home, books_dir=books_dir, syllabus_path=syllabus_path),
        "align": lambda: _run_align(rest, env_path, home=home, profile_path=profile_path),
        "chat": lambda: _run_chat(rest, env_path, profile_path=profile_path, home=home),
        "review": lambda: _run_review(rest, env_path, home=home, profile_path=profile_path, tasks_path=tasks_path),
        "explain": lambda: _run_explain(rest, env_path, home=home, profile_path=profile_path, books_dir=books_dir),
    }
    handler = handlers.get(command)
    if handler is None:
        return _usage_error(f"未知命令：{command}")
    return handler()


if __name__ == "__main__":
    raise SystemExit(main())
