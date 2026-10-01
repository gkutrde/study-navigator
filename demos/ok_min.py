# -*- coding: utf-8 -*-
"""最小可运行的 for 循环：点到谁，谁答到。

读法（Python Crash Course 第4章 L5404 的读法）：
  for 每一轮从列表里取一个名字，塞进 name 这个临时变量，
  然后执行下面所有缩进的行。列表里有几个人，就转几圈。
"""

names = ["张三", "李四", "王五", "赵六"]

for name in names:
    print(f"{name}，到！")
