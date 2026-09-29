"""T-021 失败测试：知识点命名对齐（地图点名 ↔ 画像点名）。

背景（T-010 实测结论）：

- 地图 3418 个点（书里的细粒度名字：h1 到 h6 六级标题）与画像 26 个点
  （提炼出的概括名：标题与文本格式化标签）**精确同名交集 0**；
- 于是 A-06 的「与画像最相关的书」选不出来（全 0 命中）→ 退回第一本 → 提议 main 函数；
- 纯文本匹配只覆盖 2% 且多为误报（HTML 简史 会匹配到 HTML 标签基础）。

要求：用 LLM 把地图点对齐到画像的**既有概念**；对不上的标成 new（画像里还没有的概念）。
对齐结果落盘并驱动选书/选点。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.alignment import (
    Alignment,
    align_points,
    apply_alignment,
    load_alignment,
    map_point_names,
    normalize_text,
    save_alignment,
    token_set,
)
from src.distill import KnowledgePoint
from src.profile import KnowledgeProfile
from src.syllabus import BookMap, Chapter, load_syllabus, write_syllabus


def profile_with(*names):
    return KnowledgeProfile(points=[KnowledgePoint(n, "存疑", "e") for n in names])


def book(book_name, *points):
    return BookMap(book=book_name, chapters=[Chapter("第 1 章", list(points))])


# --- 1. 文本归一化（零成本预筛，不做最终判定） --------------------------------


def test_normalize_text_lowercases_and_strips_edges():
    assert normalize_text("  HTML 标签基础（双标签/单标签） ") == "html 标签基础"


def test_token_set_splits_latin_and_cjk():
    tokens = token_set("img 标签与 src")

    assert "img" in tokens and "src" in tokens
    assert "标签" in tokens


# --- 2. LLM 对齐 ---------------------------------------------------------------


class BatchCompleter:
    """按批返回对齐结果；记录每批收到多少个点。"""

    def __init__(self, mapping=None, new_names=()):
        self.mapping = mapping or {}
        self.new_names = set(new_names)
        self.batches: list[int] = []

    def complete(self, messages):
        prompt = messages[-1]["content"]
        head = prompt.split("画像已有概念")[0]          # 只看「待对齐的点」段落，
        items = [line for line in head.splitlines() if line.startswith("- ")]  # 否则会把画像概念也数进去
        self.batches.append(len(items))
        payload = []
        for line in items:
            name = line[2:].strip()
            if name in self.mapping:
                payload.append({"point": name, "profile": self.mapping[name], "confidence": "high"})
            else:
                payload.append({"point": name, "profile": None, "confidence": "low"})
        return json.dumps(payload, ensure_ascii=False)


def test_align_points_maps_to_existing_concept():
    profile = profile_with("标题与文本格式化标签", "列表（ul/ol/li）")
    completer = BatchCompleter({
        "h1 到 h6 六级标题": "标题与文本格式化标签",
        "ul/ol/li 列表": "列表（ul/ol/li）",
    })

    aligned = align_points(["h1 到 h6 六级标题", "ul/ol/li 列表"], profile, completer=completer)

    assert aligned["h1 到 h6 六级标题"].profile == "标题与文本格式化标签"
    assert aligned["ul/ol/li 列表"].profile == "列表（ul/ol/li）"
    assert aligned["ul/ol/li 列表"].is_new is False


def test_align_points_marks_unknown_as_new():
    profile = profile_with("标题与文本格式化标签")
    completer = BatchCompleter({"h1 到 h6 六级标题": "标题与文本格式化标签"})

    aligned = align_points(["h1 到 h6 六级标题", "CSS 网格布局"], profile, completer=completer)

    assert aligned["CSS 网格布局"].profile is None
    assert aligned["CSS 网格布局"].is_new is True


def test_align_points_rejects_hallucinated_profile_name():
    """LLM 可能编出画像里没有的概念名 —— 必须丢弃，标成 new。"""
    profile = profile_with("标题与文本格式化标签")
    completer = BatchCompleter({"某点": "画像里根本没有的概念"})

    aligned = align_points(["某点"], profile, completer=completer)

    assert aligned["某点"].profile is None
    assert aligned["某点"].is_new is True


def test_align_points_batches_large_inputs():
    profile = profile_with("A")
    completer = BatchCompleter({"A": "A"})
    names = [f"点{i}" for i in range(500)]

    align_points(names, profile, completer=completer, batch_size=200)

    assert len(completer.batches) == 3
    assert all(size <= 200 for size in completer.batches)


def test_align_points_accepts_llm_json_with_extra_prose():
    class Chatty(BatchCompleter):
        def complete(self, messages):
            raw = super().complete(messages)
            return raw + "\n\n希望这份对齐结果有帮助！"

    profile = profile_with("A")
    aligned = align_points(["A"], profile, completer=Chatty({"A": "A"}))

    assert aligned["A"].profile == "A"


def test_align_points_raises_on_unusable_output():
    from src.alignment import AlignmentError

    class Broken:
        def complete(self, messages):
            return "抱歉，我无法完成"

    with pytest.raises(AlignmentError):
        align_points(["A"], profile_with("A"), completer=Broken())


# --- 3. 落盘 ------------------------------------------------------------------


def test_alignment_roundtrip(tmp_path):
    path = tmp_path / "alignment.json"
    aligned = {
        "h1 到 h6 六级标题": Alignment(point="h1 到 h6 六级标题", profile="标题与文本格式化标签", confidence="high"),
        "CSS 网格布局": Alignment(point="CSS 网格布局", profile=None, confidence="low"),
    }

    save_alignment(path, aligned)
    loaded = load_alignment(path)

    assert loaded["h1 到 h6 六级标题"].profile == "标题与文本格式化标签"
    assert loaded["CSS 网格布局"].is_new is True


def test_load_alignment_missing_file_returns_empty(tmp_path):
    assert load_alignment(tmp_path / "nope.json") == {}


def test_load_alignment_tolerates_corrupt_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ 这不是 json", encoding="utf-8")

    assert load_alignment(path) == {}


# --- 4. apply_alignment：把地图点换成画像概念 --------------------------------


def test_apply_alignment_rewrites_points_keeping_labels():
    books = [book("某书", "h1 到 h6 六级标题", "ul/ol/li 列表")]
    aligned = {
        "h1 到 h6 六级标题": Alignment("h1 到 h6 六级标题", "标题与文本格式化标签", "high"),
        "ul/ol/li 列表": Alignment("ul/ol/li 列表", "列表（ul/ol/li）", "high"),
    }

    mapped = apply_alignment(books, aligned)

    assert mapped[0].chapters[0].points == ["标题与文本格式化标签", "列表（ul/ol/li）"]


def test_apply_alignment_keeps_new_points_as_is():
    books = [book("某书", "CSS 网格布局")]
    aligned = {"CSS 网格布局": Alignment("CSS 网格布局", None, "low")}

    mapped = apply_alignment(books, aligned)

    assert mapped[0].chapters[0].points == ["CSS 网格布局"]


def test_apply_alignment_dedups_within_chapter():
    books = [book("某书", "h1 到 h6 六级标题", "标题元素 h1–h6")]
    aligned = {
        "h1 到 h6 六级标题": Alignment("h1 到 h6 六级标题", "标题与文本格式化标签", "high"),
        "标题元素 h1–h6": Alignment("标题元素 h1–h6", "标题与文本格式化标签", "high"),
    }

    mapped = apply_alignment(books, aligned)

    assert mapped[0].chapters[0].points == ["标题与文本格式化标签"]


def test_map_point_names_helper():
    aligned = {"a": Alignment("a", "A", "high"), "b": Alignment("b", None, "low")}

    assert map_point_names(aligned) == {"a": "A", "b": None}

# --- 5. A-06 接入对齐结果：选书/选点 ----------------------------------------


def test_planner_selects_book_by_alignment():
    """对齐后「与画像最相关的书」应能选出来（旧逻辑因为零重叠永远选不出）。"""
    from src.planner import next_unmet_point_for_books

    # 必须用**已掌握**状态，否则"与画像最相关"无从计算
    from src.distill import KnowledgePoint as _KP
    from src.profile import KnowledgeProfile as _Prof
    profile = _Prof(points=[
        _KP("标题与文本格式化标签", "做过", "e"),
        _KP("列表（ul/ol/li）", "学过", "e"),
        _KP("CSS 网格布局", "存疑", "e"),   # 画像里记过但未掌握 → 就是"下一个该学的"
    ])
    html_raw = [book("HTML 书", "h1 到 h6 六级标题", "ul/ol/li 列表", "CSS 网格布局")]
    cpp_raw = [book("C++ 书", "main 函数", "变量声明")]
    aligned_map = {
        "h1 到 h6 六级标题": Alignment("h1 到 h6 六级标题", "标题与文本格式化标签", "high"),
        "ul/ol/li 列表": Alignment("ul/ol/li 列表", "列表（ul/ol/li）", "high"),
        "CSS 网格布局": Alignment("CSS 网格布局", "CSS 网格布局", "high"),
    }
    html_aligned = apply_alignment(html_raw, aligned_map)
    cpp_aligned = apply_alignment(cpp_raw, {})

    point = next_unmet_point_for_books(
        cpp_aligned + html_aligned, profile, raw_books=cpp_raw + html_raw
    )

    # 应该选 HTML 书（对齐命中 2 个已掌握概念），而不是字典序第一本 C++ 书；
    # 返回**映射后的概念名**（此处即画像里那个「存疑」概念）
    assert point != "main 函数"
    assert point == "CSS 网格布局"


def test_planner_falls_back_to_raw_when_no_alignment():
    from src.planner import next_unmet_point_for_books

    profile = profile_with("标题与文本格式化标签")

    point = next_unmet_point_for_books([book("C++ 书", "main 函数")], profile)

    assert point == "main 函数"

# --- 6. CLI：align 命令 + next 使用对齐 --------------------------------


def test_cli_align_writes_alignment_file(tmp_path, monkeypatch, capsys):
    from src import cli

    profile_path = tmp_path / "profile" / "knowledge.md"
    from src.profile import write_profile_atomic

    write_profile_atomic(profile_path, KnowledgeProfile(points=[
        KnowledgePoint("标题与文本格式化标签", "做过", "e"),
        KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
    ]))
    write_syllabus(tmp_path / "profile" / "syllabus.md",
                   [book("HTML 书", "h1 到 h6 六级标题", "ul/ol/li 列表")])

    class Stub:
        def complete(self, messages):
            prompt = messages[-1]["content"]
            head = prompt.split("画像已有概念")[0]
            items = [line[2:].strip() for line in head.splitlines() if line.startswith("- ")]
            mapping = {"h1 到 h6 六级标题": "标题与文本格式化标签", "ul/ol/li 列表": "列表（ul/ol/li）"}
            return json.dumps(
                [{"point": n, "profile": mapping.get(n), "confidence": "high" if mapping.get(n) else "low"}
                 for n in items],
                ensure_ascii=False,
            )

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    code = cli.main(["align"], env_path=tmp_path / ".env", profile_path=profile_path)
    out = capsys.readouterr()

    assert code == 0, out.err
    saved = tmp_path / "profile" / "alignment.json"
    assert saved.is_file()
    aligned = load_alignment(saved)
    assert aligned["h1 到 h6 六级标题"].profile == "标题与文本格式化标签"
    assert "已对齐" in out.err or "对齐" in out.err


def test_cli_next_uses_alignment_to_pick_book(tmp_path, monkeypatch, capsys):
    """端到端：对齐后 next 应选 HTML 书里下一个未掌握概念，而不是 main 函数。"""
    from src import cli
    from src.profile import write_profile_atomic

    profile_path = tmp_path / "profile" / "knowledge.md"
    write_profile_atomic(profile_path, KnowledgeProfile(points=[
        KnowledgePoint("标题与文本格式化标签", "做过", "e"),
        KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
        KnowledgePoint("表单 form 与 input 控件", "学过", "e"),   # 凑够 MIN_POINTS=3 已掌握
        KnowledgePoint("块元素与行内元素（div/span）", "存疑", "e"),  # 记过但未掌握 → A-06 的下一个点
    ]))
    write_syllabus(tmp_path / "profile" / "syllabus.md", [
        book("C++ 书", "main 函数"),
        book("HTML 书", "标题元素 h1–h6", "ul/ol/li 列表", "div/span 布局"),
    ])
    # 三个点都要映射：没映射的点会被当成新概念（原始名），期望值就会变成原始名
    save_alignment(tmp_path / "profile" / "alignment.json", {
        "标题元素 h1–h6": Alignment("标题元素 h1–h6", "标题与文本格式化标签", "high"),
        "ul/ol/li 列表": Alignment("ul/ol/li 列表", "列表（ul/ol/li）", "high"),
        "div/span 布局": Alignment("div/span 布局", "块元素与行内元素（div/span）", "high"),
    })

    class Stub:
        def complete(self, messages):
            return json.dumps({"goal": "做一个 div 布局页", "skills": ["标题与文本格式化标签"],
                               "new_skill": "块元素与行内元素（div/span）", "acceptance": "能看到",
                               "steps": []}, ensure_ascii=False)

    monkeypatch.setattr(cli, "make_llm_completer", lambda **kw: Stub())
    code = cli.main(["next"], env_path=tmp_path / ".env", profile_path=profile_path,
                    tasks_path=tmp_path / "tasks.md")
    out = capsys.readouterr()

    assert code == 0, out.err
    assert "块元素与行内元素（div/span）" in out.out
    assert "main 函数" not in out.out

# --- 7. 对齐后新暴露：书的序言/导读被当成知识点 ------------------------------


def test_next_unmet_point_skips_front_matter_points():
    """实测：对齐后选中的书里，第一个"未掌握点"是「这本书的适用读者」——
    那是书的**序言/导读**，不是可出题的知识点。
    """
    from src.planner import next_unmet_point_for_books

    from src.profile import KnowledgeProfile as _Prof
    from src.distill import KnowledgePoint as _KP

    profile = _Prof(points=[
        _KP("标题与文本格式化标签", "做过", "e"),
        _KP("列表（ul/ol/li）", "学过", "e"),
        _KP("表单 form 与 input 控件", "学过", "e"),
    ])
    # 书的开头是导读类条目，真正的知识点在后面
    books = [book("HTML 书",
                  "这本书的适用读者", "学习原理六条", "元认知与主动学习",
                  "标题元素 h1–h6", "ul/ol/li 列表")]

    point = next_unmet_point_for_books(books, profile)

    assert point == "标题元素 h1–h6"


def test_front_matter_detection():
    from src.planner import is_front_matter

    assert is_front_matter("这本书的适用读者")
    assert is_front_matter("学习原理六条")
    assert is_front_matter("给读者的九条作业")
    assert is_front_matter("版权声明")
    assert not is_front_matter("标题元素 h1–h6")
    assert not is_front_matter("列表（ul/ol/li）")


def test_front_matter_skipped_in_single_book_helper():
    from src.planner import _first_unmet_in_book

    book_map = book("某书", "这本书的适用读者", "真实的第一个知识点")

    assert _first_unmet_in_book(book_map, set()) == "真实的第一个知识点"

def test_intro_chapter_detection():
    from src.planner import is_intro_chapter

    assert is_intro_chapter("Intro 导读")
    assert is_intro_chapter("导读")
    assert is_intro_chapter("前言")
    assert is_intro_chapter("Introduction")
    assert not is_intro_chapter("第 1 章 认识 HTML")
    assert not is_intro_chapter("第 2 章 深入超文本")


def test_next_unmet_point_skips_whole_intro_chapter():
    """实测：真实地图里《Head First HTML 与 CSS》第 1 章就叫「Intro 导读」，
    里面 8 个条目（适用读者/学习原理/元认知/慢路与快路学习…）全是书的导读，不是知识点。
    """
    from src.planner import next_unmet_point_for_books
    from src.syllabus import BookMap, Chapter as _Ch
    from src.profile import KnowledgeProfile as _Prof
    from src.distill import KnowledgePoint as _KP

    profile = _Prof(points=[
        _KP("标题与文本格式化标签", "做过", "e"),
        _KP("列表（ul/ol/li）", "学过", "e"),
        _KP("表单 form 与 input 控件", "学过", "e"),
    ])
    html = BookMap(book="HTML 书", chapters=[
        _Ch("Intro 导读", ["这本书的适用读者", "学习原理六条", "慢路与快路学习"]),
        _Ch("第 1 章 认识 HTML", ["h1 到 h6 六级标题", "ul 与 ol 列表"]),
    ])

    point = next_unmet_point_for_books([html], profile)

    assert point == "h1 到 h6 六级标题"

def test_book_with_no_remaining_mapped_point_falls_through_to_next_book():
    """实测：选中书里高置信度点**全部已掌握**时，不该硬塞一个未映射的零碎条目，
    应该跳到下一本与画像相关的书。
    """
    from src.planner import next_unmet_point_for_books
    from src.syllabus import BookMap, Chapter as _Ch
    from src.profile import KnowledgeProfile as _Prof
    from src.distill import KnowledgePoint as _KP
    from src.alignment import Alignment as _A

    profile = _Prof(points=[
        _KP("标题与文本格式化标签", "做过", "e"),
        _KP("列表（ul/ol/li）", "学过", "e"),
        _KP("字典", "存疑", "e"),          # 画像里记过但未掌握
    ])
    html_raw = [BookMap(book="HTML 书", chapters=[
        _Ch("第 1 章", ["h1 到 h6 六级标题", "浏览器与服务器的工作原理"]),
    ])]
    py_raw = [BookMap(book="Python 书", chapters=[_Ch("第 1 章", ["键值对", "列表推导式"])])]
    amap = {
        "h1 到 h6 六级标题": _A("h1 到 h6 六级标题", "标题与文本格式化标签", "high"),
        "键值对": _A("键值对", "字典", "high"),
    }
    books = apply_alignment(html_raw, amap) + apply_alignment(py_raw, amap)

    point = next_unmet_point_for_books(books, profile, raw_books=html_raw + py_raw)

    assert point == "字典"
