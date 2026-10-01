# -*- coding: utf-8 -*-
"""序号交给 enumerate，别自己养计数器。

enumerate(names, start=1) 每一轮吐两个东西：
  第一个是序号（从 start 开始数），第二个是元素本身。
左边用 i, name 两个名字一起接住 —— 这叫"解包"。
"""

names = ["张三", "李四", "王五", "赵六", "欧阳小明"]

title = "自定义班级"
print(title)

for i, name in enumerate(names, start=1):
    print(f"{i}. {name}")

# 这行没缩进，所以循环结束了才执行一次（第4章 L5509）
print(f"共计 {len(names)} 人")
