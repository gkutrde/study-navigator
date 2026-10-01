# -*- coding: utf-8 -*-
"""半成品①：for 头改成 enumerate 了，但忘了删循环体里的 i += 1。

跑之前先猜：序号会翻倍（1,3,5,7,9）还是照常（1,2,3,4,5）？
"""
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in enumerate(class_name, start=1):
    print(f"{i}.{student_name}")
    i += 1          # ← 改的时候忘了删这一行

print(f"共计{len(class_name)}人")
