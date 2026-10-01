# -*- coding: utf-8 -*-
"""错法一：忘了缩进（第4章 L5543 Forgetting to Indent）

预期报错：IndentationError: expected an indented block after 'for' statement on line 4
"""

names = ["张三", "李四", "王五", "赵六"]
for name in names:
print(name)
