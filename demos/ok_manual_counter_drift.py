# -*- coding: utf-8 -*-
"""手动 i += 1 和 enumerate 的分水岭：跳过一个名字时，序号开始漂。

两段代码做同一件事：跳过"李四"，打印其余的人。
看序号 —— 手动计数器给的是"第几个被打印的人"，
enumerate 给的是"这个人在名单里的位置"。你要哪个？

（continue 的意思是：本轮到此为止，直接进下一轮。第7章 L7982。）
"""

names = ["张三", "李四", "王五", "赵六"]

print("=== A：手动计数器 i += 1 ===")
i = 1
for name in names:
    if name == "李四":
        continue          # 跳过本轮，i += 1 也跟着被跳过
    print(f"{i}. {name}")
    i += 1

print()
print("=== B：enumerate ===")
for i, name in enumerate(names, start=1):
    if name == "李四":
        continue          # 只跳过这一轮，序号由名单位置决定，不受影响
    print(f"{i}. {name}")

print()
print("A 的序号断了联系，B 的序号始终等于名单位置 —— 这就是它不容易错的原因。")
