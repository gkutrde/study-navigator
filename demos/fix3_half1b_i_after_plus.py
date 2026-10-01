# -*- coding: utf-8 -*-
"""半成品①的延伸：忘了删的 i += 1 现在是「废行」——但只在它后面没代码时才无害。

在 i += 1 之后加一行打印，它立刻开始说谎：同一轮里，i 说着已经被 +1 的数字，
下一轮开头又被 enumerate 按名单位置重新发号。
"""
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in enumerate(class_name, start=1):
    print(f"{i}.{student_name}")
    i += 1
    print(f"     ← 这行看到 i = {i}")   # 同一轮里 i 已经变了

print(f"共计{len(class_name)}人")
