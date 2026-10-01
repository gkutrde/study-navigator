# -*- coding: utf-8 -*-
"""半成品②：两行删掉了，但忘了把 for 头改成 enumerate。

i = 1 和 i += 1 都删了，循环体里却还在用 i —— 这行代码活着，但 i 已经没人发给它了。
"""
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for student_name in class_name:

    print(f"{i}.{student_name}")   # i 是谁？没人定义过

print(f"共计{len(class_name)}人")
