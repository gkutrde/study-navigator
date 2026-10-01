# 点名册那一课：把书翻到该翻的那几页

> 材料全在你自己的工作区里，没有一句是我凭记忆写的。
> 书：`books\_src\python-crash-course.txt`（20640 行）、`begin-js-dom-sc-ajax.txt`（12228 行）、`cpp-primer-5e.txt`（245171 行）
> 索引：`books\_src\*.index.md`（章节标题 → 行号）
> 行号口径与索引表一致，随时可复核。

## 0. 先装个开书的手

我写了 `read-book.ps1`。以后不用问我"这在哪"，自己一句话打开：

```powershell
.\read-book.ps1 python 5402            # Python Crash Course L5402 起，40 行
.\read-book.ps1 python 5402 -Count 135 # 想多看点
.\read-book.ps1 js 1689 -Count 75      # JS 那本 for 循环那一节
.\read-book.ps1 cpp 21109 -Count 40    # C++ Primer vector
.\read-book.ps1 python -Index          # 有哪些书 / 索引表在哪
```

下面每一段我都给了行号 —— 打开书，对着读。

---

## 1. 「列表」（已学过，只对一遍）· PCC 第 3 章

- 章首 **L4849**，定义在 **L4854** `## What Is a List?`

书里第 4856 行那句定义：

> A list is a collection of items in a particular order.
> （列表是**按特定顺序**排列的一堆东西。）
> Because a list usually contains more than one element, it's a good idea to make the name of your list plural.

最后一句话直接对着你写的 `class_name` 来的。你写的是 `class_name`（单数），装的是 5 个名字。书里建议叫 `names` / `class_names` —— 复数名一读就知道这是"整个列表"，`for` 里的 `student_name` 才是"单个元素"。**单数变量装单个、复数变量装一堆**，这条比它看起来重要，下面第 3 节还要用到。

- **L4873** Accessing Elements in a List：`bicycles[0]`，取单个元素时**不带方括号输出**
- **L4899** Index Positions Start at 0, Not 1。原话：

> Python considers the first item in a list to be at position 0, not position 1. ... If you're receiving unexpected results, ask yourself if you're making a simple but common off-by-one error.

这就是 `enumerate(..., start=1)` 要写 `start=1` 的原因：**列表内部从 0 数，人从 1 数**，`start=1` 就是把这套账翻译一次。
- **L4927** Using Individual Values from a List：`message = f"My first bicycle was a {bicycles[0].title()}."` —— f-string 里塞列表元素，正是你 `f"{i}. {student_name}"` 的原型。
- **L5300** Finding the Length of a List 就是你的 `len()`：

```
>>> cars = ['bmw', 'audi', 'toyota', 'subaru']
>>> len(cars)
4
```

**L5314** 那句 Note 值得抄进本子：

> Python counts the items in a list starting with one, so you shouldn't run into any off-by-one errors when determining the length of a list.
> （`len()` 从 1 开始数，所以**长度**这块没有差一错误。）

对照记牢：**索引从 0，长度从 1**。`names[0]` 是第一个人，`len(names)` 是人数。

---

## 2. 本次唯一新点：for 循环 · PCC 第 4 章 **L5397**

章标题 `# 4 Working with Lists`（L5398）。

### 2.1 它为什么存在 —— L5402

> You'll often want to run through all entries in a list, performing the same task with each item. ... When you want to do the same action with every item in a list, you can use Python's for loop.
> （要对列表里每一项做同一件事时，就用 `for`。）

**L5405** 这句是全书对你这次作业最直接的判决：

> We could do this by retrieving each name from the list individually, but this approach could cause several problems. For one, it would be repetitive to do this with a long list of names. Also, **we'd have to change our code each time the list's length changed.**
> （一个个手动取元素有两个毛病：人多了要重复写；**名单长度一变，代码就得跟着改**。）

`for` 解决的就是这两件事：**写一次，循环自己走完整个列表**。

### 2.2 形状与读法 —— L5410

```python
magicians = ['alice', 'david', 'carolina']
for magician in magicians:
    print(magician)
```

L5415 的读法，建议你背这一句：

> It might help to read this code as "**For every magician in the list of magicians, print the magician's name.**"
> （对名单里的每一个 magician，打印它的名字。）

### 2.3 Python 内部一轮一轮在干什么 —— L5423「A Closer Look at Looping」

书里把三轮拆得很细，L5431–L5449：

1. 读 `for magician in magicians:` → 取出第一个值 `'alice'`，绑给 `magician`
2. 读下一行 `print(magician)` → 打印 `alice`
3. 列表还有值 → **回到 for 那一行**，取 `'david'`，绑给同一个 `magician`（覆盖掉上一个）
4. 再打印 → `david` → 再回头取 `'carolina'` → 打印 → 列表空了 → **走到 for 后面那行继续执行**

两个结论：
- **临时变量每轮被重新赋值**，`magician` 的名字从头到尾就这一个，不是三个变量
- **循环结束 = 列表取空**，程序从 for 之后接着跑 —— 这是你 `共计 X 人` 那行该待的位置（下一节）

L5450 是"循环的力气"那句话：

> If you have a million items in your list, Python repeats these steps a million times—and usually very quickly.

L5451–L5459 讲命名，就是我第 1 节说的那条：

> choose a meaningful name that represents a single item from the list. ... `for cat in cats:` / `for dog in dogs:` / `for item in list_of_items:` ... Using singular and plural names can help you identify whether a section of code is working with a single element from the list or the entire list.

### 2.4 循环体里多做几件事 —— L5461「Doing More Work Within a for Loop」

L5481 是关键规则：

> Every indented line following the line `for magician in magicians` is considered **inside the loop**, and each indented line is executed once for each value in the list.

**缩进 = 在循环里；顶格 = 在循环外。** 只有这一条判据，Python 不靠花括号。

### 2.5 循环结束之后 —— L5506「Doing Something After a for Loop」

> Any lines of code after the for loop that are **not indented** are executed **once** without repetition.

例子里那句 `print("Thank you, everyone. That was a great magic show!")` 顶格，所以只出现一次（L5511–L5533）。
你的 `print(f"共计 {len(class_name)} 人")` 就属于这一行 —— 你这次的缩进是对的，验收里"最后一行总人数"正是考点。

---

## 3. 验收里那句话的出处：五种缩进错法 · L5537「Avoiding Indentation Errors」

任务卡上写着"如果循环体缩进错了会看到报错或格式混乱，可作为自查点"——**这一整节就是为它写的**（L5539–L5541）：

> it uses whitespace to **force you to write neatly formatted code** ... people sometimes indent lines of code that don't need to be indented or forget to indent lines that need to be indented.

我把五种错法各写成一个能跑的文件，放在 `demos\`，**真实输出贴在下面**（Python 3.14.7，我本机实跑）。

### 错法一：忘了缩进 —— L5543，`demos\err1_forget_indent.py`

书里的报错原文（L5560）：`IndentationError: expected an indented block after 'for' statement on line 2`

我实跑的回包：

```
  File "...\demos\err1_forget_indent.py", line 9
    print(name)
    ^^^^^
IndentationError: expected an indented block after 'for' statement on line 8
```

书 L5563 的解法：把 for 后面紧跟的那行（或那几行）缩进。

### 错法二：第二行忘了缩进 —— L5565，`demos\err2_forget_more_indent.py`

**不报错。** 书 L5577 的说法：

> because Python finds at least one indented line after the for statement, it doesn't report an error. ... The second print() call is not indented, so it is executed only once after the loop has finished running.

我实跑的回包：

```
张三，到！
李四，到！
王五，到！
赵六，到！
这句话本想每人说一遍，但没缩进，所以只在循环结束后说了一次：赵六
```

每一轮都换人的那句话被踢出循环了，而且 `name` 停在最后一个值 `赵六` —— 书 L5586 把它叫 **logical error（逻辑错误）**：语法合法，结果不对。

### 错法三：多缩进了不该缩进的行 —— L5588，`demos\err3_unexpected_indent.py`

报错 `IndentationError: unexpected indent`。实测：

```
  File "...\demos\err3_unexpected_indent.py", line 8
    print(message)
IndentationError: unexpected indent
```

书 L5607 的一句硬规矩：**"the only lines you should indent are the actions you want to repeat for each item in a for loop."**（现在这个阶段，只有你想"每人重复一次"的行才该缩进。）

### 错法四：循环结束后那行被缩进了 —— L5609，`demos\err4_indent_after_loop.py`

书 L5624 的原文：`Because the last line is indented, it's printed once for each person in the list.` 实测：

```
张三，到！
共计 4 人
李四，到！
共计 4 人
王五，到！
共计 4 人
赵六，到！
共计 4 人
```

**"共计 4 人"被打了 4 次** —— 你要验收的"最后一行总人数"如果缩进错，出来的就是这个样子。书 L5641 给的判据很好用：

> If an action is repeated many times when it should be executed only once, you probably need to **unindent** the code for that action.

### 错法五：忘了冒号 —— L5643，`demos\err5_forget_colon.py`

实测：`SyntaxError: expected ':'`（书 L5659 一样）。
书 L5662 还顺手安慰了一句：`Don't feel bad when a small fix takes a long time to find; you are absolutely not alone in this experience.`

---

## 4. 你为什么会写出 `i = 1` / `i += 1`

因为书上另有一本在教另一种 for。任务卡把"for 循环"挂到 JS 那本（`begin-js-dom-sc-ajax.txt`），出处没错 —— 它在第 2 章最末尾：

- **L1689「重复的事情:循环」**，骨架在 **L1695**：`for( initial-condition; loop-condition; alter-condition ) { ... }`
- L1704 三部分的解释：**第一部分初始化计数器变量，第二部分测条件，第三部分递增/递减这个计数器**
- L1708：`for( loopCounter = 1; loopCounter <= 10; loopCounter++ )`
- L1719 遍历数组：`for ( var loopCounter = 0; loopCounter < theBeatles.length; loopCounter++ )`

看清楚了：**JS 的 for 没有人给你元素和序号，你必须自己养一个 `loopCounter`、自己判条件、自己 `++`。** 你写的 `i = 1` + `i += 1` 就是这套三件套的肌肉记忆。

Python 把这三件事全包了：

| | JS | Python |
|---|---|---|
| 谁给元素 | 自己 `arr[loopCounter]` | `for name in names:` 直接递给你 |
| 谁管边界 | 自己判 `loopCounter < arr.length` | 列表取空自然停 |
| 谁管递增 | 自己 `loopCounter++` | 不用写 |
| 谁给序号 | 自己 `loopCounter` | `enumerate(names, start=1)` |

所以：**书该读，但读的时候要翻一次译**。JS 那章的 for 是"计数循环"，Python 的 `for` 是"遍历循环" —— 你照 JS 的手感写 Python，就会绕开本次唯一的新点。

---

## 5. `enumerate` 在哪 —— PCC 第 16 章 **L14702**

```
for index, column_header in enumerate(header_row):
    print(index, column_header)
```

L14706 那句定义（**这是全书对 `enumerate` 唯一一句教学**）：

> The `enumerate()` function returns **both the index of each item and the value of each item** as you loop through a list.

注意书里没写 `start=1` —— 因为解析 CSV 表头时它要的就是从 0 开始的列号（输出 L14710–L14715 是 `0 STATION` / `1 NAME` …）。**你要的是人名编号，所以必须 `start=1`。**

书的作者把 `enumerate` 排在"处理数据"阶段（第 16 章，书上 331 页），第 4 章只教 `for x in 列表`。**所以你还算越级借了件工具**——它不是本次作业的必答项，是加分项；但既然已经借了，就借对。

---

## 6. 你代码里另外两处空格问题，书上有明文 · L6128、L6139

- **L6133 The Style Guide**：PEP 8。
- **L6141 Indentation**：`PEP 8 recommends that you use four spaces per indentation level.` —— 你用 4 空格，**达标**。同节还警告 `Mixing tabs and spaces in your file can cause problems that are very difficult to diagnose.`（编辑器里设成"TAB 键插入空格"，别混。）
- **L6147 Line Length**：一行 80 字符以内。
- **L6155 Blank Lines**：空行分组，别堆三四个连续空行。
- 你原文 `class_name =["小明",...]` 的等号和方括号之间少个空格、`共计5人` 少个空格 —— 这类"运算符/参数两侧留空格"在 PEP 8 正文档里，书里这节只是开了个头（L6162 明说 `most of the guidelines refer to more complex programs than what you're writing at this point`）。想直接看原文：`https://python.org/dev/peps/pep-0008`（书 L6166 的习题 4-14 就是让你去读它）。

---

## 7. 那个"图谱映射"错在哪（顺带结清）

任务卡把"列表"挂到《C++ Primer》第 15 章 面向对象程序设计 —— **错的**。C++ 里对应 Python list 的是 `vector`：

- **`cpp-primer-5e.index.md` 第 17 行**：`L21109  Chapter 3. Strings, Vectors, and Arrays` ← vector 登场
- **第 24 行**：`L77806  Chapter 9. Sequential Containers` ← 顺序容器的正式章节
- 第 15 章是 OOP（继承、虚函数、动态绑定），跟列表零关系

自己打开看：`.\read-book.ps1 cpp 21109 -Count 40`

---

## 8. 实跑实验：序号到底该怎么发 · `demos\`

上面每个文件都能直接跑：

```powershell
python -X utf8 demos\ok_min.py
python -X utf8 demos\ok_enumerate.py
python -X utf8 demos\ok_manual_counter_drift.py
python -X utf8 demos\err1_forget_indent.py     # 到 err5 都行，故意报错的
```

`demos\ok_min.py` 真实输出（最小 for 的形状）：

```
张三，到！
李四，到！
王五，到！
赵六，到！
```

`demos\ok_enumerate.py` 真实输出（顺手带上任务要点 9 的长名字自查）：

```
自定义班级
1. 张三
2. 李四
3. 王五
4. 赵六
5. 欧阳小明
共计 5 人
```

`demos\ok_manual_counter_drift.py` 真实输出 —— **这一份是重点**，同一件事（跳过"李四"）：

```
=== A：手动计数器 i += 1 ===
1. 张三
2. 王五
3. 赵六

=== B：enumerate ===
1. 张三
3. 王五
4. 赵六
```

A 是"第几个念到的人"，B 是"这个人在名单里排第几"。**`i += 1` 在 `continue` 那一轮被跳过了**，序号就和名单脱钩了；`enumerate` 的序号由名单位置决定，跳一轮它照样数到 2。你以后写"跳过已到的人再编号"这类需求时，这个差别就是 bug 与不 bug 的差别。

---

## 9. 你那份 roster.py 的成品版

```python
class_name = ["小明", "小红", "小白", "小蓝", "小绿"]

print("自定义班级")

for i, student_name in enumerate(class_name, start=1):
    print(f"{i}. {student_name}")

print(f"共计 {len(class_name)} 人")
```

三处改动，一一对应上面：
1. 删 `i = 1`、删 `i += 1`，序号交给 `enumerate(..., start=1)`（第 2.5 节的"循环外" + 第 5 节）
2. `f"{i}. {student_name}"` 补上点号后的空格（第 6 节 PEP 8 / 验收原句）
3. `共计 {len(class_name)} 人` 补空格，且**顶格**（第 2.5 节、错法四）

---

## 10. 欠你的同类小练习

> 起手文件：`demos\practice_starter.py`（骨架 + 自查题，已建好）

**题：我的书架 `bookshelf.py`**

1. 建一个书单 `books`，放 5 本，其中**至少一本名字明显更长**（中英混着来更好，比如 `"流畅的Python"` 和 `"Python编程：从入门到实践"`）
2. 打印一行标题 `我的书架`
3. 用 `for` + `enumerate(books, start=1)` 逐本打印，格式 **`序号. 书名`**（点号后有空格）
4. 循环**结束后**打印 `共计 5 本`（用 `len()`，别手写数字）
5. 输出里不得出现多余空格；序号列不得因书名长短而漂

**验收自查表**（自己跑一遍，逐条打勾）：

- [ ] 标题一行，在名单前面
- [ ] 5 行书名，序号 1→5 递增、不重复、不跳号
- [ ] 点号后是一个空格，`1. 流畅的Python`，不是 `1.流畅的Python`
- [ ] 最后一行 `共计 5 本` **只出现一次** —— 如果出现 5 次，去看错法四（`demos\err4_indent_after_loop.py`）
- [ ] 最后一行**顶格**，没被吞进循环里
- [ ] 把长书名换到第 2 位再跑一次，序号列对齐依旧

**交完再加一个小实验**（就是上面第 8 节那件事的复用）：

在循环体里加三行，跳过第 3 本：

```python
    if i == 3:
        continue
```

先猜输出什么样（提示：`continue` 干什么，见第 7 章 `L7982`），再跑，再回答我一句：**我猜的和实跑的差在哪、为什么。**

---

## 11. 附：这轮创建的东西

| 文件 | 干什么 |
|---|---|
| `read-book.ps1` | 按行号打开书，带行号打印（第 0 节用法） |
| `demos\ok_min.py` | 最小 for 循环 |
| `demos\ok_enumerate.py` | `enumerate(start=1)` + 长名字对齐自查 |
| `demos\ok_manual_counter_drift.py` | 手动计数器 vs enumerate，`continue` 下的分水岭 |
| `demos\err1..err5_*.py` | 书上五种缩进/冒号错法，各一份可跑复现 |
| `demos\practice_starter.py` | 第 10 节练习的骨架 |
| `notes\for循环-读书页.md` | 本文 |

**回滚**：以上全是新增文件，删掉即可 —— `Remove-Item -Recurse -Force demos\practice_starter.py, demos\ok_*.py, demos\err*.py, notes\for循环-读书页.md, read-book.ps1`。没有改动你任何原有文件。
