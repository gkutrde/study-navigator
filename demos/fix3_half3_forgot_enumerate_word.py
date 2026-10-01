# -*- coding: utf-8 -*-
"""半成品③：for 头写成了 for i, student_name in class_name:（漏掉 enumerate 这个函数名）。

这是最阴的一种：不报错，序号不见了，名字被从中间劈成两半。
五个两字名全过；把「小蓝」换成四字的「欧阳小明」再跑一次，当场见真章。
"""
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in class_name:
    print(f"{i}.{student_name}")

print(f"共计{len(class_name)}人")
