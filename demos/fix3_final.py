# -*- coding: utf-8 -*-
"""第三点的成品：序号交给 enumerate，删掉 i = 1 和 i += 1。

对照 roster.py.bak（LO 提交版）看，改动只有三处：
  删  i = 1
  改  for student_name in class_name:  →  for i, student_name in enumerate(class_name, start=1):
  删  i += 1
循环体里那行 print 一个字没动 —— i 这个名字还在，只是发号的人换了。
"""
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in enumerate(class_name, start=1):
    print(f"{i}.{student_name}")

print(f"共计{len(class_name)}人")
