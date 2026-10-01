# -*- coding: utf-8 -*-
"""练习骨架：我的书架  →  存成 bookshelf.py 后自己填空

目标输出（5 本书、第 2 位是长书名时也一样对齐）：

    我的书架
    1. 流畅的Python
    2. Python编程：从入门到实践
    3. 算法图解
    4. 代码整洁之道
    5. 深入理解计算机系统
    共计 5 本

要求：
  1) 循环体里用 enumerate(books, start=1)，不要自己养 i
  2) 格式 f"{序号}. {书名}"，点号后面有一个空格
  3) 「共计 ... 本」在循环【外】，用 len()，只出现一次

跑法：python -X utf8 demos/practice_starter.py
"""

# --- 1. 书单（把长书名放第 2 位，用来验序号列会不会漂） ---
books = [
    "流畅的Python",
    # TODO: 再加 4 本，其中至少一本名字明显更长
]


# --- 2. 标题 ---
# TODO: 打印一行「我的书架」


# --- 3. 循环：序号由 enumerate 发 ---
# TODO: for i, book in enumerate(books, start=1):
#           在这行下面【缩进 4 格】打印 f"{i}. {book}"


# --- 4. 循环结束后顶格打印总数 ---
# TODO: print(f"共计 {len(books)} 本")


# --- 5. 自查实验（留到最后再做）---
# 在循环体里加：
#     if i == 3:
#         continue
# 先写出你预测的输出，再跑，再解释差在哪。
# 提示：continue 见 python-crash-course.txt 第 7 章 L7982；对照 ok_manual_counter_drift.py。


print("骨架已加载：上面 3 处 TODO 填完，再删掉这行。")
