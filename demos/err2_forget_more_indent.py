# -*- coding: utf-8 -*-
"""错法二：第二行忘了缩进（第4章 L5565 Forgetting to Indent Additional Lines）

不报错！但只有最后一个人收到了第二句话 —— 逻辑错误（logical error）。
"""

names = ["张三", "李四", "王五", "赵六"]
for name in names:
    print(f"{name}，到！")
print(f"这句话本想每人说一遍，但没缩进，所以只在循环结束后说了一次：{name}")
