"""T-042 失败测试：出题 prompt 的地图必须与**选点依据**同一本书。

实测的错位：
- 选点走 "next_unmet_point_for_books" → 挑「与画像最相关」的书（HTML）；
- 但 prompt 里的地图固定塞 books_map[0]（C++ Primer 全章节，5901 字符）。
于是 LLM 看到 C++ 地图、却被要求按 HTML 的点出题。

修法：只放**选中那本书**，且只含选中点所在章 ± 前后各一章，目标 ≤2000 字符，
并附一行全图摘要。
"""
from __future__ import annotations

import pytest

from src.profile import KnowledgeProfile, KnowledgePoint
from src.syllabus import BookMap, Chapter


def book(name, chapters):
    """chapters: [(章名, [点...]), ...]"""
    return BookMap(book=name, chapters=[Chapter(c, list(p)) for c, p in chapters])


def html_book():
    return book("HTML 书", [
        ("第 1 章 结构", ["HTML 文档结构", "块元素与行内元素"]),
        ("第 2 章 列表", ["列表（ul/ol/li）", "超链接 a 标签"]),
        ("第 3 章 表格", ["表格（table/tr/th/td）"]),
        ("第 4 章 表单", ["表单 input 标签"]),
    ])


def cpp_book():
    return book("C++ Primer", [
        ("第 1 章 起步", ["C++ 开发工具安装", "第一个 C++ 程序"]),
        ("第 2 章 变量", ["变量与基本类型", "main 函数"]),
        ("第 3 章 字符串", ["string 类型"]),
    ])


def profile_learning_html():
    """画像正在学 HTML：只有 HTML 的点被掌握。"""
    return KnowledgeProfile(points=[
        KnowledgePoint("HTML 文档结构", "学过", "e"),
        KnowledgePoint("块元素与行内元素", "学过", "e"),
        KnowledgePoint("列表（ul/ol/li）", "做过", "e"),
    ])


# ---------- 选书与选点要一起返回 ----------


def test_pick_book_and_point_returns_the_selected_book():
    from src.planner import pick_book_and_point

    chosen = pick_book_and_point([cpp_book(), html_book()], profile_learning_html())

    assert chosen is not None
    book_obj, point = chosen
    assert book_obj.book == "HTML 书", "应当选中画像最相关的 HTML 书，而不是第一本 C++"
    assert point, "要给出该书的未掌握点"


def test_next_unmet_point_for_books_still_works():
    """老接口保持兼容（别把既有调用方弄坏）。"""
    from src.planner import next_unmet_point_for_books

    point = next_unmet_point_for_books([cpp_book(), html_book()], profile_learning_html())

    assert point
    assert point in {"表格（table/tr/th/td）", "超链接 a 标签", "表单 input 标签"}


# ---------- prompt 里的地图只放选中那本书 ----------


def test_prompt_map_is_the_selected_book(tmp_path):
    """验收：prompt 中地图书名 == expected_new 所属书。"""
    from src.planner import build_next_messages, pick_book_and_point

    books = [cpp_book(), html_book()]
    profile = profile_learning_html()
    chosen = pick_book_and_point(books, profile)
    assert chosen is not None

    messages = build_next_messages(profile, book=chosen[0], focus_point=chosen[1])
    blob = str(messages)

    assert "HTML 书" in blob, "prompt 里必须有选中那本书"
    assert "C++ Primer" not in blob, "prompt 里不该出现没被选中的书"


def test_prompt_map_only_has_nearby_chapters():
    """只含选中点所在章 ± 前后各一章。"""
    from src.planner import build_next_messages

    chosen = html_book()
    messages = build_next_messages(
        profile_learning_html(), book=chosen, focus_point="表格（table/tr/th/td）"
    )
    blob = str(messages)

    assert "第 3 章 表格" in blob, "选中点所在的章必须在"
    assert "第 2 章 列表" in blob, "前一章要在"
    assert "第 4 章 表单" in blob, "后一章要在"
    assert "第 1 章 结构" not in blob, "隔了两章的（第 1 章）不该在"


def test_prompt_map_has_overall_summary_line():
    from src.planner import build_next_messages

    messages = build_next_messages(
        profile_learning_html(), book=html_book(), focus_point="表格（table/tr/th/td）"
    )
    blob = str(messages)

    assert "摘要" in blob, "要附一行全图摘要"
    assert "4 章" in blob or "共 4" in blob, "摘要里要有总章数"


def test_prompt_map_stays_short():
    """目标 ≤2000 字符：真实 C++ Primer 全书 5901 字符就是被这条挡下的问题。"""
    from src.planner import build_next_messages

    big = book("大部头", [
        (f"第 {i} 章 " + "标题" * 8, [f"知识点 {i}-{j}" + "说明" * 4 for j in range(12)])
        for i in range(1, 41)
    ])
    messages = build_next_messages(
        profile_learning_html(),
        book=big,
        focus_point="知识点 20-3说明说明说明说明",
    )
    blob = str(messages)

    assert len(blob) < 6000, "整段 prompt 不该被地图撑爆（实测：" + str(len(blob)) + " 字符）"
    assert "第 40 章" not in blob, "远章不该出现"


def test_no_book_gives_summary_only():
    """没有任何书时退回单本 dict 的老路径（不能崩）。"""
    from src.planner import build_next_messages

    messages = build_next_messages(profile_learning_html())
    blob = str(messages)

    assert "知识地图" in blob
    assert "没有知识地图" in blob, "没有地图时给明确说明"


def test_single_syllabus_dict_still_supported():
    """老的 syllabus dict 路径还要能用（别的调用方还在传）。"""
    from src.planner import build_next_messages

    messages = build_next_messages(
        profile_learning_html(),
        syllabus={"book": "老地图", "chapters": [{"chapter": "第 1 章", "points": ["X"]}]},
    )
    blob = str(messages)

    assert "老地图" in blob


# ---------- 回归：A-03 / A-06 的约束不能被破坏 ----------


def test_a06_expected_new_still_from_selected_book():
    """A-06：任务的新点必须是**地图里那本书**的下一个未掌握点。"""
    from src.planner import next_unmet_point_for_books

    point = next_unmet_point_for_books([cpp_book(), html_book()], profile_learning_html())

    html_points = {
        p for ch in html_book().chapters for p in ch.points
    }
    assert point in html_points, "A-06 的点必须来自被判为「正在学」的那本书"


def test_a03_uncertain_points_not_in_map_points():
    """A-03：地图里列出的点只能是"还没掌握"的，不能把已掌握的算成待学。"""
    from src.planner import next_unmet_point_for_books

    profile = KnowledgeProfile(points=[
        KnowledgePoint("HTML 文档结构", "学过", "e"),
        KnowledgePoint("块元素与行内元素", "学过", "e"),
        KnowledgePoint("列表（ul/ol/li）", "学过", "e"),
        KnowledgePoint("超链接 a 标签", "学过", "e"),
    ])

    point = next_unmet_point_for_books([html_book()], profile)

    assert point == "表格（table/tr/th/td）", "已掌握的点不能再被当作下一个待学点"

# ---------- 端到端：真走 generate_task，抓实际发出的 prompt ----------


class CapturingCompleter:
    """记下收到的 messages，然后回一个合规的 JSON。

    skill 可以指定：桩声明的知识点必须在调用方的画像里，否则会被越界机制拦下。
    """

    def __init__(self, skill: str = "HTML 文档结构"):
        self.calls = []
        self.skill = skill

    def complete(self, messages):
        self.calls.append(str(messages))
        import json as _json

        return _json.dumps({
            "goal": "做一个练习页",
            "skills": [self.skill],
            "new_skill": None,
            "steps": ["写结构"],
            "acceptance": "浏览器能打开",
            "reason": "r",
        }, ensure_ascii=False)


def test_e2e_prompt_book_equals_expected_new_book():
    """**验收原句**：prompt 中地图书名 == expected_new 所属书。"""
    from src.planner import generate_task, pick_book_and_point

    books = [cpp_book(), html_book()]
    profile = profile_learning_html()
    completer = CapturingCompleter()

    # 关掉题库路径（不给 assignments），逼它走 LLM 分支——那样才发 prompt
    generate_task(profile, completer=completer, books=books, attempts=1)

    assert completer.calls, "应当调用过 LLM"
    prompt = completer.calls[0]

    expected = pick_book_and_point(books, profile)
    assert expected is not None
    expected_book, expected_point = expected

    assert expected_book.book in prompt, "prompt 里要有 expected_new 所属的那本书"
    assert expected_point in prompt, "prompt 里要给出那个点"
    # 没被选中的书不允许出现在地图里（这正是旧的错位）
    for other in books:
        if other.book == expected_book.book:
            continue
        assert other.book not in prompt, "没被选中的书不该出现在 prompt：" + other.book


def test_e2e_prompt_map_is_shorter_than_full_book():
    """地图段落必须明显短于整本书（旧实现 5901 字符）。"""
    from src.planner import generate_task

    big = book("大部头", [
        (f"第 {i} 章 " + "标题" * 10, [f"点 {i}-{j}" + "说明" * 6 for j in range(15)])
        for i in range(1, 61)
    ])
    # 至少 3 个已掌握点（MIN_POINTS），且必须**真的在大部头里**才会被算作相关
    profile = KnowledgeProfile(points=[
        KnowledgePoint("点 30-1" + "说明" * 6, "学过", "e"),
        KnowledgePoint("点 30-2" + "说明" * 6, "学过", "e"),
        KnowledgePoint("点 30-3" + "说明" * 6, "学过", "e"),
    ])
    # 桩要声明画像里真有的点，否则会被越界机制拦下（这条测的是 prompt 长度）
    completer = CapturingCompleter(skill="点 30-1" + "说明" * 6)

    generate_task(profile, completer=completer, books=[big], attempts=1)

    prompt = completer.calls[0]
    assert "第 60 章" not in prompt, "第 60 章离选中点太远，不该出现"
    assert "全图摘要" in prompt, "要有全图摘要"