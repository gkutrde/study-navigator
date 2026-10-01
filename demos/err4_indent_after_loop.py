# -*- coding: utf-8 -*-
"""错法四：循环结束后该顶格的行，被缩进了（第4章 L5609 Indenting Unnecessarily After the Loop）

不报错！总计行被打了 4 次 —— 逻辑错误。
"""

names = ["张三", "李四", "王五", "赵六"]
for name in names:
    print(f"{name}，到！")
    print(f"共计 {len(names)} 人")
