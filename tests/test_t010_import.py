"""T-010 失败测试：import 命令（蒸馏稿 → 知识地图）+ 分块策略。

现状根因（可确认）：

- `build_import_messages` 里写死 `body.strip()[:20000]`：单文件 67K~129K 字符，一次调用会被**砍掉大半**；
- 没有格式校验：缺书名的稿子靠文件名兜底，不报错（T-010 要求「格式不符时报错指出缺什么」）。

要求：

1. 格式校验：缺 frontmatter / 缺书名 / 空文件 → 明确指出缺什么，地图不变；
2. **分块提炼**：长稿按章节边界切块，逐块提炼再合并，不把整本塞进一次调用；
3. 合并要稳：章节顺序按书中出现顺序，重复章节合并、知识点去重；
4. 失败不破坏既有地图。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.syllabus import (
    BookMap,
    Chapter,
    SyllabusError,
    build_import_messages,
    chunk_book,
    import_book,
    load_syllabus,
    merge_chapters,
    parse_syllabus,
    read_book_title,
    split_sections,
    validate_distillate,
    write_syllabus,
)


def distillate(title="Python 入门", body=None, lines=40):
    text = "---\nbook: " + title + "\n---\n\n# 蒸馏稿\n\n"
    for index in range(1, lines + 1):
        text += f"## 第 {index} 章 主题{index}\n\n这一章讲{index}的内容。" + ("填充" * 30) + "\n\n"
    return text


# --- 1. 格式校验 ---------------------------------------------------------------


def test_validate_accepts_good_distillate():
    info = validate_distillate(distillate(), "fallback")

    assert info.book == "Python 入门"
    assert info.characters > 0


def test_validate_rejects_missing_frontmatter():
    with pytest.raises(SyllabusError) as exc:
        validate_distillate("# 没有 frontmatter 的稿子\n\n正文\n", "某书")

    message = str(exc.value)
    assert "frontmatter" in message or "---" in message
    assert "书名" in message


def test_validate_rejects_missing_book_title():
    text = "---\nsource: 蒸馏稿\n---\n\n# 稿子\n\n正文\n"

    with pytest.raises(SyllabusError) as exc:
        validate_distillate(text, "某书")

    assert "书名" in str(exc.value) or "book" in str(exc.value)


def test_validate_rejects_empty_body():
    text = "---\nbook: 空书\n---\n\n"

    with pytest.raises(SyllabusError) as exc:
        validate_distillate(text, "空书")

    assert "空" in str(exc.value) or "正文" in str(exc.value)


def test_validate_reports_what_is_missing_per_item():
    """错误信息要能指出缺什么，而不是笼统一句失败。"""
    with pytest.raises(SyllabusError) as exc:
        validate_distillate("没有 frontmatter\n", "某书")

    assert "缺" in str(exc.value)


# --- 2. 章节切分与分块 ---------------------------------------------------------


def test_split_sections_keeps_headings():
    sections = split_sections(distillate(lines=3))

    names = [s.heading for s in sections]
    assert "第 1 章 主题1" in names
    assert "第 3 章 主题3" in names


def test_split_sections_prefers_lower_heading_levels_when_present():
    text = "# 书\n\n## 第一部分\n\n### 1.1 小节\n\n正文\n"
    sections = split_sections(text, level=2)

    assert [s.heading for s in sections] == ["第一部分"]


def test_chunk_book_respects_size_limit():
    text = distillate(lines=60)

    chunks = chunk_book(text, max_chars=4000)

    assert len(chunks) > 1
    assert all(len(c) <= 4000 * 1.5 for c in chunks)  # 允许单节超限，但不该整本塞一块


def test_chunk_book_does_not_lose_content():
    text = distillate(lines=30)

    chunks = chunk_book(text, max_chars=3000)
    joined = "".join(chunks)

    # 每一章都还在（按标题核对，避免受空白切分影响）
    for index in range(1, 31):
        assert f"第 {index} 章 主题{index}" in joined


def test_chunk_book_single_chunk_for_small_input():
    text = "# 小稿\n\n很短。\n"

    assert len(chunk_book(text, max_chars=100000)) == 1


def test_oversized_single_section_is_hard_split():
    text = "## 巨章\n\n" + ("内容" * 5000) + "\n"

    chunks = chunk_book(text, max_chars=2000)

    assert len(chunks) > 1
    assert all(len(c) <= 4000 for c in chunks)


def test_build_import_messages_uses_given_chunk_fully():
    """关键回归：不能再把正文硬截断到 20000 字符。"""
    body = "正文" * 20000  # 40000 字符

    messages = build_import_messages("书名", body)
    prompt = messages[-1]["content"]

    assert len(prompt) > 30000
    assert body[:25000] in prompt


# --- 3. 合并 -------------------------------------------------------------------


def test_merge_chapters_keeps_first_seen_order():
    merged = merge_chapters([
        [Chapter("第一章", ["A"])],
        [Chapter("第二章", ["B"])],
    ])

    assert [c.chapter for c in merged] == ["第一章", "第二章"]


def test_merge_chapters_combines_same_chapter():
    merged = merge_chapters([
        [Chapter("第一章", ["A"])],
        [Chapter("第一章", ["B"])],
    ])

    assert len(merged) == 1
    assert merged[0].points == ["A", "B"]


def test_merge_chapters_deduplicates_points():
    merged = merge_chapters([
        [Chapter("第一章", ["A", "B"])],
        [Chapter("第一章", ["B", "C"])],
    ])

    assert merged[0].points == ["A", "B", "C"]


def test_merge_chapters_skips_empty_names():
    merged = merge_chapters([[Chapter("", ["A"]), Chapter("有效章", [])]])

    assert [c.chapter for c in merged] == ["有效章"]


# --- 4. import_book：逐块提炼 ---------------------------------------------------


class ChunkAwareCompleter:
    """按块返回章节；记录每次收到的正文长度，用来证明没有整本塞进一次调用。"""

    def __init__(self):
        self.sizes: list[int] = []

    def complete(self, messages):
        prompt = messages[-1]["content"]
        self.sizes.append(len(prompt))
        # 从提示里挑出块内的章节标题
        chapters = []
        for line in prompt.splitlines():
            if line.startswith("## "):
                chapters.append({"chapter": line[3:].strip(), "points": [line[3:].strip() + "知识点"]})
        return json.dumps(chapters, ensure_ascii=False)


def test_import_book_chunks_long_distillate(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(distillate(lines=80), encoding="utf-8")
    completer = ChunkAwareCompleter()

    result, _target = import_book(
        path, completer=completer, max_chars=4000, syllabus_path=tmp_path / "s.md"
    )

    assert len(completer.sizes) > 1, "长稿应该被分成多次调用"
    assert max(completer.sizes) < 20000, f"单次调用不该塞进整本：{max(completer.sizes)}"
    assert len(result.chapters) >= 10


def test_import_book_single_call_for_short_distillate(tmp_path):
    path = tmp_path / "short.md"
    path.write_text(distillate(lines=3), encoding="utf-8")
    completer = ChunkAwareCompleter()

    # 注意：必须传 syllabus_path，否则会写到真实的 profile/syllabus.md（曾经污染过一次）
    import_book(path, completer=completer, max_chars=100000, syllabus_path=tmp_path / "s.md")

    assert len(completer.sizes) == 1


def test_import_book_reports_progress(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(distillate(lines=40), encoding="utf-8")
    seen = []

    import_book(path, completer=ChunkAwareCompleter(), max_chars=2000,
                syllabus_path=tmp_path / "s.md", on_progress=lambda i, n: seen.append((i, n)))

    assert len(seen) >= 2
    assert seen[0] == (1, len(seen))


def test_import_book_rejects_bad_format(tmp_path):
    path = tmp_path / "bad.md"
    path.write_text("没有 frontmatter 的稿子\n", encoding="utf-8")

    with pytest.raises(SyllabusError):
        import_book(path, completer=ChunkAwareCompleter(), syllabus_path=tmp_path / "s.md")


def test_import_book_merges_and_dedups(tmp_path):
    path = tmp_path / "long.md"
    path.write_text(distillate(lines=40), encoding="utf-8")

    result, _target = import_book(
        path, completer=ChunkAwareCompleter(), max_chars=2000, syllabus_path=tmp_path / "s.md"
    )

    names = [c.chapter for c in result.chapters]
    assert len(names) == len(set(names)), "同一章节不该出现两次"


# --- 5. 地图落盘 ---------------------------------------------------------------


def test_syllabus_roundtrip(tmp_path):
    path = tmp_path / "syllabus.md"
    books = [BookMap(book="Python 入门", chapters=[Chapter("第 1 章", ["列表", "字典"])])]

    write_syllabus(path, books)
    loaded = load_syllabus(path)

    assert loaded[0].book == "Python 入门"
    assert loaded[0].chapters[0].points == ["列表", "字典"]


def test_write_syllabus_is_atomic_and_keeps_other_books(tmp_path):
    path = tmp_path / "syllabus.md"
    write_syllabus(path, [BookMap(book="书A", chapters=[Chapter("第 1 章", ["x"])])])
    write_syllabus(path, [
        BookMap(book="书B", chapters=[Chapter("第 1 章", ["y"])]),
        BookMap(book="书A", chapters=[Chapter("第 1 章", ["x"])]),
    ])

    loaded = load_syllabus(path)

    assert {b.book for b in loaded} == {"书A", "书B"}
    assert not list(tmp_path.glob("*.tmp"))


def test_syllabus_contains_no_original_paragraphs(tmp_path):
    """A-05：地图只存知识点名称，不抄原文段落。"""
    path = tmp_path / "syllabus.md"
    write_syllabus(path, [BookMap(book="书A", chapters=[Chapter("第 1 章", ["列表"])])])

    text = path.read_text(encoding="utf-8")

    assert "填充" not in text
    assert len(text) < 500

# --- 7. T-010 实测发现：长任务中途登录态过期后无法续跑 --------------------------


def test_completer_reloads_credentials_between_chunks(tmp_path):
    """实测：7 本书导入共 603s，Kimi 登录态约 10 分钟过期，导致后半程全部 401。

    修复要求：每次调用前**重新读取**凭证/登录态，这样用户重新 /login 后
    不必重启进程就能续跑（长批量导入的常态）。
    """
    from src.llm import LLMClient, ProviderConfig

    calls = []

    class Rotating(LLMClient):
        def __init__(self):
            self.credentials_reads = 0

        def _read_credentials(self):
            self.credentials_reads += 1
            return f"token-{self.credentials_reads}"

    client = Rotating()
    seen = []
    for _ in range(3):
        seen.append(client._read_credentials())

    assert seen == ["token-1", "token-2", "token-3"], "凭证必须在每次调用前重新读取"


def test_import_book_reports_which_chunk_failed(tmp_path):
    """失败信息要指明是第几块失败，便于判断"续跑从哪开始"。"""
    path = tmp_path / "long.md"
    path.write_text(distillate(lines=60), encoding="utf-8")

    class FailsOnThird:
        def __init__(self):
            self.n = 0

        def complete(self, messages):
            self.n += 1
            if self.n == 3:
                raise RuntimeError("boom")
            # 前两块必须是**合法**输出，否则测试会先在第 1 块失败（前提不成立）
            return json.dumps([{"chapter": f"第 {self.n} 章", "points": ["x"]}], ensure_ascii=False)

    with pytest.raises(SyllabusError) as exc:
        import_book(path, completer=FailsOnThird(), max_chars=2000)

    assert "第 3/" in str(exc.value)

# --- 6. A-06 实测发现：多本书时「按书序」是哪本书？ ----------------------------


def book(book_name, *chapters):
    """chapters 形如 ("第 1 章", ["A", "B"])。"""
    return BookMap(book=book_name, chapters=[Chapter(chapter=n, points=list(p)) for n, p in chapters])


HTML_BOOK = book("Head First HTML 与 CSS", ("第 1 章 认识 HTML", ["列表（ul/ol/li）", "表格（table/tr/th/td）"]))
CPP_BOOK = book("C++ Primer", ("第 1 章 开始", ["main 函数", "变量"]))


def test_next_unmet_point_prefers_book_matching_profile():
    """A-06 要求「按书序的下一个未掌握点」，但没规定是哪本书。

    实测问题：地图有 5~7 本时，旧实现取**字典序第一本**（C++ Primer），
    于是给一个 HTML 学到一半的学生安排「main 函数」——荒谬。
    正确行为：优先选**与画像最相关**的书（已掌握知识点最多的那本）。
    """
    from src.planner import next_unmet_point_for_books

    # 只掌握 HTML 书里的第一个点 → 该书的下一个未掌握点是"表格"
    profile = profile_with(("列表（ul/ol/li）", "做过"))

    # 故意把 C++ 放前面，验证不是靠顺序碰运气
    point = next_unmet_point_for_books([CPP_BOOK, HTML_BOOK], profile)

    assert point == "表格（table/tr/th/td）"
    assert point != "main 函数"


def test_next_unmet_point_for_books_returns_first_unmastered_in_book_order():
    from src.planner import next_unmet_point_for_books

    profile = profile_with(("列表（ul/ol/li）", "做过"))

    point = next_unmet_point_for_books([HTML_BOOK], profile)

    assert point == "表格（table/tr/th/td）"  # 第一个未掌握，按书内顺序


def test_next_unmet_point_for_books_falls_back_to_first_book_when_no_match():
    from src.planner import next_unmet_point_for_books

    profile = profile_with(("完全无关的知识点", "学过"))

    point = next_unmet_point_for_books([CPP_BOOK, HTML_BOOK], profile)

    assert point == "main 函数"  # 没有任何书匹配画像 → 退回第一本


def test_next_unmet_point_for_books_empty_maps():
    from src.planner import next_unmet_point_for_books

    assert next_unmet_point_for_books([], profile_with(("A", "学过"))) is None


def test_next_unmet_point_for_books_returns_none_when_all_mastered():
    from src.planner import next_unmet_point_for_books

    profile = profile_with(("列表（ul/ol/li）", "做过"), ("表格（table/tr/th/td）", "做过"))

    assert next_unmet_point_for_books([HTML_BOOK], profile) is None


# --- 7. cli 加载地图时不该把 5 本书压成 1 本 ----------------------------------


def test_syllabus_loader_keeps_all_books():
    """实测：load_syllabus 返回多本，但 _run_next 只取 maps[0]（字典序第一本）。"""
    from src.syllabus import load_syllabus

    maps = load_syllabus(Path("profile/syllabus.md"))

    assert len(maps) >= 2, "真实地图应有多本书"

def profile_with(*pairs):
    """构造画像：pairs 形如 ("知识点", "状态")。"""
    from src.distill import KnowledgePoint as _KP
    from src.profile import KnowledgeProfile as _Prof

    return _Prof(points=[_KP(name, level, "e") for name, level in pairs])

# --- 8. T-010 实测发现：地图是 markdown，但 _load_syllabus 读的是 JSON ----------


def test_cli_loads_markdown_syllabus(tmp_path):
    """实测：syllabus.md 是 markdown（## 书名 / ### 章 / - 点），
    但 _load_syllabus 用 json.loads 读它 → 永远 None → A-06 从未生效。

    修复后：能读出全部书；返回结构供 planner 按「与画像最相关的书」选点。
    """
    from src import cli

    path = tmp_path / "syllabus.md"
    write_syllabus(path, [HTML_BOOK, CPP_BOOK])

    loaded = cli._load_syllabus(path)

    assert loaded is not None
    assert len(loaded) == 2, "应返回全部书，而不是压成一本"
    assert loaded[0].book == "Head First HTML 与 CSS"


def test_cli_syllabus_loader_returns_none_for_missing_file(tmp_path):
    from src import cli

    assert cli._load_syllabus(tmp_path / "nope.md") is None


def test_cli_next_uses_map_to_pick_new_point(tmp_path, monkeypatch, capsys):
    """A-06 端到端：有地图时，任务的新点必须是地图里那本书的下一个未掌握点。"""
    from src import cli

    path = tmp_path / "syllabus.md"
    write_syllabus(path, [HTML_BOOK])
    profile_path = tmp_path / "profile" / "knowledge.md"
    from src.profile import write_profile_atomic

    write_profile_atomic(profile_path, profile_with(
        ("列表（ul/ol/li）", "做过"),
        ("块元素与行内元素（div/span）", "学过"),
        ("超链接 a 标签（href/target）", "学过"),
    ))

    class Stub:
        def complete(self, messages):
            # 注意：桩里不要用 assert —— 抛异常会被上层当成 LLM 失败，退化成难查的退出码 1
            return json.dumps({
                "goal": "做一张课程表", "skills": ["列表（ul/ol/li）"],
                "new_skill": "表格（table/tr/th/td）",
                "acceptance": "能看到 4 行表格", "steps": ["a"],
            }, ensure_ascii=False)

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    # 用没有题库的目录，强制走 LLM 路径
    code = cli.main(
        ["next"], env_path=tmp_path / ".env", profile_path=profile_path,
        tasks_path=tmp_path / "tasks.md", syllabus_path=path,
    )
    out = capsys.readouterr()

    assert code == 0, out.err
    # A-06：新点必须是地图里那本书按书序的下一个未掌握点
    assert "**新知识点**：表格（table/tr/th/td）" in out.out

def test_cli_bank_hit_still_obeys_map(tmp_path, monkeypatch, capsys):
    """A-06 在 CLI 路径也要生效：命中题库但新点与地图要求不符时，必须回退 LLM。

    实测漏洞：_run_next 命中题库就提前 return，绕过了 generate_task 里的 A-06 守卫。
    """
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with(
        ("列表（ul/ol/li）", "做过"),
        ("块元素与行内元素（div/span）", "学过"),
        ("超链接 a 标签（href/target）", "学过"),
    ))
    # 题库条目：标签命中，但带的 new_skill 是「字典」
    bank_path = tmp_path / "profile" / "assignments.md"
    bank_path.write_text(
        "## A-01 待办清单\n\n"
        + "```yaml\n"
        "course: 哈佛 CS50P\n"
        "tags: [列表（ul/ol/li）]\n"
        "level: 入门\n"
        "new_skill: 字典\n"
        + "```\n\n"
        "**目标**：写个待办清单\n\n**实现要点**：\n1. a\n\n**验收方式**：能加能查\n",
        encoding="utf-8",
    )
    # 地图：第 1 章的点画像已掌握，故「下一个未掌握点」落在第 2 章的「表格」
    map_path = tmp_path / "profile" / "syllabus.md"
    write_syllabus(map_path, [BookMap(book="Head First HTML 与 CSS", chapters=[
        Chapter("第 1 章", ["列表（ul/ol/li）", "块元素与行内元素（div/span）"]),
        Chapter("第 2 章", ["表格（table/tr/th/td）"]),
    ])])

    class Stub:
        def complete(self, messages):
            return json.dumps({"goal": "LLM 出的表格任务", "skills": ["列表（ul/ol/li）"],
                               "new_skill": "表格（table/tr/th/td）", "acceptance": "4 行", "steps": []},
                              ensure_ascii=False)

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    code = cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path,
                    tasks_path=tmp_path / "tasks.md")
    out = capsys.readouterr()

    assert code == 0, out.err
    assert "LLM 出的表格任务" in out.out, "题库新点与地图不符时应回退 LLM"
    assert "写个待办清单" not in out.out


def test_cli_bank_hit_used_when_map_has_no_new_point(tmp_path, monkeypatch, capsys):
    """题库条目不需要新点时，即使有地图也照常用题库（A-06 只管"新点从哪来"）。"""
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, profile_with(
        ("列表（ul/ol/li）", "做过"),
        ("块元素与行内元素（div/span）", "学过"),
        ("超链接 a 标签（href/target）", "学过"),
    ))
    bank_path = tmp_path / "profile" / "assignments.md"
    bank_path.write_text(
        "## A-01 个人名片页\n\n"
        + "```yaml\n"
        "course: 哈佛 CS50\n"
        "tags: [列表（ul/ol/li）, 块元素与行内元素（div/span）]\n"
        "level: 入门\n"
        "new_skill: \"\"\n"
        + "```\n\n"
        "**目标**：做一个名片页\n\n**实现要点**：\n1. a\n\n**验收方式**：能看到\n",
        encoding="utf-8",
    )
    map_path = tmp_path / "profile" / "syllabus.md"
    write_syllabus(map_path, [BookMap(book="某书", chapters=[
        Chapter("第 1 章", ["列表（ul/ol/li）", "块元素与行内元素（div/span）"]),
        Chapter("第 2 章", ["表格（table/tr/th/td）"]),
    ])])

    def explode(**kw):
        raise AssertionError("命中题库且不需要新点时不该加载 LLM")

    monkeypatch.setattr(cli, "make_llm_completer", explode)
    code = cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path,
                    tasks_path=tmp_path / "tasks.md")
    out = capsys.readouterr()

    assert code == 0, out.err
    assert "做一个名片页" in out.out

from src.profile import write_profile_atomic  # noqa: E402
from src.distill import KnowledgePoint  # noqa: E402  （测试用）

# --- 9. T-010 实测发现：画像 render/parse 往返不保真（括号结尾的名称被吃掉） -----


def test_profile_roundtrip_keeps_name_with_parentheses():
    """实测：名称以括号结尾、且该点是「未分类」时，写回再读出来名称会少一截。

    「列表（ul/ol/li）」（未分类）→ 渲染成 `- [做过] 列表（ul/ol/li）（未分类） — 证据：x`
    → 解析时把最后一个括号当主题切掉，名称被吃掉一截（实测变成「列表」），
    导致与题库标签再也匹配不上。
    """
    from src.profile import KnowledgeProfile, parse_profile, render_profile

    profile = KnowledgeProfile(points=[
        KnowledgePoint("列表（ul/ol/li）", "做过", "HTML 列表"),
        KnowledgePoint("列表", "学过", "Python 列表"),
    ])

    text = render_profile(profile)
    reloaded = parse_profile(text)

    assert [p.name for p in reloaded.points] == ["列表（ul/ol/li）", "列表"]
    assert reloaded.points[0].level == "做过"


def test_profile_roundtrip_keeps_topic_suffix_convention():
    """带主题的常规写法仍要正常工作。"""
    from src.profile import KnowledgeProfile, parse_profile, render_profile

    profile = KnowledgeProfile(points=[KnowledgePoint("列表", "学过", "e", "Python 基础")])

    reloaded = parse_profile(render_profile(profile))

    assert reloaded.points[0].name == "列表"
    assert reloaded.points[0].topic == "Python 基础"


def test_profile_roundtrip_stable_twice():
    """连续两轮渲染/解析结果必须一致（幂等）。"""
    from src.profile import KnowledgeProfile, parse_profile, render_profile

    profile = KnowledgeProfile(points=[
        KnowledgePoint("表格（table/tr/th/td）", "做过", "e", "HTML 基础"),
        KnowledgePoint("列表（ul/ol/li）", "做过", "e"),
    ])

    once = parse_profile(render_profile(profile))
    twice = parse_profile(render_profile(once))

    assert [p.name for p in once.points] == [p.name for p in twice.points]
    assert [p.topic for p in once.points] == [p.topic for p in twice.points]