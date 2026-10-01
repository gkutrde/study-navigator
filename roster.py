# -*- coding: utf-8 -*-
# roster.py —— 班级点名册（最小修改版：三处空格 + enumerate 接管序号）
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in enumerate(class_name, start=1):
    print(f"{i}. {student_name}")

print(f"共计 {len(class_name)} 人")
