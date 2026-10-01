# -*- coding: utf-8 -*-
"""错法三：多缩进了不该缩进的行（第4章 L5588 Indenting Unnecessarily）

预期报错：IndentationError: unexpected indent
"""

message = "点名开始"
    print(message)
