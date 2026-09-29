# 知识地图

## C++ Primer（第 5 版）

### 第 1 章 开始

- main 函数
- iostream 库
- cin/cout/cerr/clog
- 注释
- while 与 for 循环
- if 语句
- Sales_item 类初览
- 书店程序
- 函数定义四要素
- 函数体与块
- 语句与分号
- 源文件与头文件
- #include 指令
- 表达式
- 输出运算符 <<
- 字符串字面值
- 操纵符 endl
- 缓冲区刷新
- 标准流对象 cin/cout/cerr/clog
- IDE 与命令行编译
- 警告选项

### 第 2 章 变量和基本类型

- 类型决定含义与操作
- 算术类型
- void 类型
- char 与字符类型族
- 整型大小保证
- 类型位数随机器变化
- char 与 signed char
- 无符号类型范围
- 有符号类型范围
- 引用必须初始化
- 左值与右值
- 类型与内置类型
- 变量
- char 与宽字符类型
- signed 与 unsigned
- 字节与机器字

### 第 3 章 字符串、向量和数组

- string 与 vector 是数组的抽象
- using 声明
- 空 vector 与运行时添加
- 范围 for 语句
- array 容器
- 内置数组不支持拷贝赋值
- assign 成员
- 容器赋值类型要求
- vector
- 范围 for
- 迭代器
- array
- 数组与指针

### 第 4 章 表达式

- 表达式定义
- 一元二元运算符
- 优先级与结合性
- 小整型提升
- 操作数转换
- 重载运算符
- 输出运算符链式调用
- 表达式与运算符
- 左值与右值
- 求值顺序
- 显式转换

### 第 5 章 语句

- 简单语句
- 空语句
- 块与作用域
- 多余分号陷阱
- if 语句
- switch 语句
- 循环语句
- try 块与异常
- 复合语句与块作用域
- 控制流语句
- 异常入门 try/throw

### 第 6 章 函数

- 函数定义要素
- 调用运算符
- fact 阶乘示例
- 局部对象
- 分离编译
- 参数传递
- 函数重载
- 默认实参
- inline 与 constexpr
- 函数指针
- 函数与调用运算符
- 返回类型
- 函数匹配

### 第 7 章 类

- 数据抽象
- 接口与实现分离
- 封装
- 抽象数据类型
- Sales_data 反例
- 构造函数
- 友元
- 类作用域
- 委托构造
- 聚合类
- static 成员
- Sales_item 与 Sales_data 对比
- 成员函数
- 返回 *this
- 隐式转换与聚合类

### 第 8 章 IO 库

- IO 由库处理
- iostream/fstream/sstream 三分
- 宽字符版本
- ifstream 继承 istream
- IO 对象不可拷贝赋值
- endl 与缓冲区刷新
- IO 头文件
- IO 类型继承关系
- 文件流与文件模式

### 第 9 章 顺序容器

- 容器初始化与赋值
- swap 与 assign
- 容器增删访问
- 迭代器失效
- vector 增长
- forward_list
- string 操作
- 容器适配器
- 容器通用操作
- assign 成员
- array 容器特性

### 第 10 章 泛型算法

- 泛型算法定义
- 迭代器划定范围
- find 算法
- 算法与容器无关
- 算法依赖元素类型操作
- lambda 表达式
- bind
- 五种迭代器类别
- 插入迭代器
- 反向迭代器
- 泛型算法
- 迭代器类别
- 算法与容器解耦
- 捕获与返回

### 第 11 章 关联容器

- key 存取
- 八个关联容器分类
- map 关联数组
- set 判断存在性
- map 下标插入新元素
- set 无下标
- multimap 无下标
- pair
- 无序容器
- 词频统计
- 关联容器
- 关联数组
- map
- set
- multi 前缀
- unordered 前缀
- map 下标陷阱

### 第 12 章 动态内存

- 动态对象生命周期
- new 表达式
- delete 表达式
- 内存泄漏
- 悬垂指针
- shared_ptr
- unique_ptr
- weak_ptr
- 动态数组
- allocator
- 智能指针
- 自由存储区
- 动态分配对象
- new/delete 两步式
- 文本查询程序

### 第 13 章 拷贝控制

- 五个特殊成员函数
- 拷贝构造函数
- 合成拷贝构造
- 三/五法则
- 像值与像指针
- swap
- 右值引用
- 左值引用绑定规则
- 移动语义
- 引用限定成员函数
- 拷贝控制五成员
- 合成的拷贝构造
- 拷贝赋值运算符
- 析构函数
- 移动构造与移动赋值
- = default
- = delete
- 左值引用
- 引用折叠
- std::move
- std::forward
- noexcept

### 第 14 章 重载运算与类型转换

- 运算符重载
- 输入输出运算符
- 下标运算符
- 函数调用运算符
- 函数对象
- lambda 是函数对象
- function 类型
- 转换运算符
- 函数匹配
- 重载运算符
- 类型转换与二义性

### 第 15 章 面向对象程序设计

- OOP 三概念
- 基类与派生类
- public 派生
- 虚函数
- override 说明符
- 抽象基类
- 动态绑定
- 虚析构
- 继承下的作用域
- 多重继承
- 虚继承
- 继承
- 派生列表
- virtual 虚函数
- override
- final
- 虚析构函数
- 访问控制

### 第 16 章 模板与泛型编程

- OOP 与泛型的类型时机之分
- 函数模板
- 模板参数列表不能为空
- 模板推断的极少转换
- 顶层 const 被忽略
- std::move
- std::forward
- 引用折叠
- 可变参数模板
- 参数包
- 模板
- 模板参数列表
- 模板参数与模板实参
- 实例化
- 实参推断的极少转换
- 函数模板 compare
- 特例化
- OOP 与泛型编程对比

### 第 17 章 标准库特殊设施

- tuple
- bitset
- 正则表达式
- 随机数
- IO 再探
- function 类模板
- 函数对象

### 第 18 章 大型程序工具

- 异常分离检测与解决
- throw 行为
- 栈展开
- 未捕获异常
- noexcept
- 异常类层次
- 命名空间
- 多重继承需求

### 第 19 章 特殊工具与技术

- 重载 operator new/delete
- 定位 new
- RTTI
- dynamic_cast 与 typeid
- 枚举
- 成员指针
- 嵌套类
- union
- 局部类
- operator new/delete
- dynamic_cast
- typeid 与 type_info
- 位域
- volatile
- extern "C"

### 第 1 章 Getting Started

- 函数定义四要素
- main 返回值
- IO 标准库与四个 IO 对象
- 链式输出原理
- endl 与缓冲区刷新
- 编译命令 g++ / cl
- 警告选项
- 书店贯穿案例

### 第 2 章 Variables and Basic Types

- 类型的根本地位
- 算术类型分类
- 位数随机器变化
- char 的三种身份
- 有符号与无符号范围
- 类型选择实用规则
- C++11 新特性

### 第 3 章 Strings, Vectors, and Arrays

- 抽象数据类型 string 与 vector
- using 声明
- vector 运行时增长
- 范围 for 的序列要求
- 范围 for 禁止改变大小

### 第 4 章 Expressions

- 表达式定义
- 运算符分类
- 符号重载身份
- 优先级与结合性
- 求值顺序
- 操作数类型转换
- 整型提升
- 重载运算符

### 第 5 章 Statements

- 控制流语句
- 表达式语句
- 空语句
- 多余分号陷阱
- 块与作用域

### 第 6 章 Functions

- 函数定义
- 调用运算符
- 形参与实参
- 阶乘函数示例
- 分离编译
- 参数传递方式
- 数组形参退化
- 函数匹配与重载
- C++11 新特性
- assert 与默认实参

### 第 7 章 Classes

- 数据抽象
- 封装
- 抽象数据类型判据
- Sales_item 与 Sales_data 对比
- 类设计三章路线

### 第 8 章 The IO Library

- IO 由标准库定义
- iostream/fstream/sstream 分工
- 宽字符版本
- 继承与设备无关
- IO 对象不可拷贝不可赋值

### 第 9 章 Sequential Containers

- 顺序容器
- array 容器化数组
- array 赋值限制
- assign 成员
- 迭代器失效
- vector 增长策略
- 容器适配器
- C++11 新特性

### 第 10 章 Generic Algorithms

- 泛型算法概念
- algorithm 与 numeric 头文件
- 迭代器范围机制
- find 用法与返回值
- find 通吃容器与数组
- 子范围查找
- find 六步分解
- 迭代器使算法与容器无关

### 第 11 章 Associative Containers

- 关联容器与顺序容器差别
- map 与 set
- 八容器三维分类
- 无序容器与哈希
- 头文件归属
- map 关联数组
- 词频统计示例
- map 下标插入元素
- 哪些关联容器无下标

### 第 12 章 Dynamic Memory

- 对象生命周期三种来源
- 动态对象定义
- 智能指针的必要性
- shared_ptr/unique_ptr/weak_ptr
- 自由存储区
- new 表达式三步
- delete 表达式两步
- 动态数组限制
- allocator
- 文本查询项目

### 第 13 章 Copy Control

- 五个特殊成员函数
- 编译器合成拷贝控制
- 三/五法则
- 右值引用
- 左值与右值语义
- 引用绑定规则
- 拷贝构造函数判定规则
- 拷贝构造不应 explicit
- 合成的拷贝构造函数
- 析构调用计数练习

### 第 14 章 Overloaded Operations and Conversions

- 重载运算符即重载函数
- 输出运算符返回 ostream&
- lambda 是函数对象
- function 类模板
- 转换运算符
- 用户定义转换歧义
- 重载运算符函数匹配

### 第 15 章 Object-Oriented Programming

- OOP 三概念
- 继承与动态绑定
- 基类与派生类
- 虚函数 virtual
- 派生列表与 public 继承
- override 说明符
- 动态绑定与 print_total
- Quote 与 Bulk_quote 示例

### 第 16 章 Templates and Generic Programming

- OOP 与泛型编程对比
- 为什么需要模板
- 函数模板定义
- 模板参数列表
- 模板参数与函数参数类比
- 模板实参推断
- 模板推断的转换限制
- 可变参数模板
- 参数包

### 第 17 章 Specialized Library Facilities

- tuple
- bitset
- 正则库
- 随机数引擎与分布
- IO 再探

### 第 18 章 Tools for Large Programs

- 大程序三需求
- 异常设计目标
- throw 后果
- 栈展开
- 异常不可忽略
- noexcept
- 命名空间
- 多重继承与虚继承

### 第 19 章 Specialized Tools and Techniques

- new 表达式与 operator new 分层
- 重载全局 new/delete
- 定位 new
- RTTI 与 dynamic_cast
- 枚举
- 成员指针
- union 与嵌套类
- extern "C"

### 第 18 章 用于大型程序的工具

- 异常处理
- 栈展开
- noexcept 说明符
- 命名空间
- using 声明

## Head First HTML 与 CSS（第 2 版）

### Intro 导读

- 这本书的适用读者
- 学习原理六条
- 元认知与主动学习
- 慢路与快路学习
- 给读者的九条作业
- 结构呈现分离原则
- 80/20 取舍
- 双浏览器对照测试

### 第 1 章 认识 HTML

- 浏览器与服务器的工作原理
- 标签与元素的构成
- h1 到 h6 六级标题
- html/head/title/body 文档骨架
- HTML 注释语法
- 浏览器忽略空白
- style 标签必须放在 head 里
- 第一条 CSS 规则
- HTML 管结构 CSS 管表现
- 基本页面结构
- 标题元素 h1–h6
- 段落元素
- 标签与元素
- id 属性
- 内嵌样式
- margin 与 padding
- font-family
- HTML 管结构 CSS 管呈现

### 第 2 章 深入超文本

- a 标签创建超链接
- href 属性指定目的地
- 属性的语法与写法
- 属性值必须加双引号
- 不能自定义属性
- 相对路径规划
- 路径排查

### 第 3 章 网页构造

- 从草图到大纲到页面的建站流程
- q 短引用
- blockquote 长引用
- ul 与 ol 列表
- 嵌套元素
- 元素嵌套关系图
- 内联元素与块级元素
- 嵌套
- 块级元素
- 内联元素
- 元素树
- 浏览器容错

### 第 4 章 连接上网

- 托管与域名
- FTP 上传文件
- 绝对路径
- index.html 默认页
- 链接到其他网站
- id 做页面内锚点
- target 开新窗口

### 第 5 章 添加图像

- 图像的额外请求
- img 标签与 src
- alt 替代文本
- 图片尺寸问题
- 缩略图
- 缩略图变链接
- GIF 透明
- JPEG 适合照片
- PNG 无损透明
- matte 底色匹配
- img 的 src 与 alt
- JPEG/PNG/GIF 选择
- 图片做链接
- 断图可读性

### 第 6 章 标准与校验

- HTML 简史
- quirks mode
- doctype 文档类型声明
- W3C 校验器
- meta 声明编码
- strict doctype
- 修复嵌套错误
- 遵循标准的收益

### 第 7 章 迁移到 XHTML

- XML 是什么
- XML 与 HTML 的关系
- 为什么用 XHTML
- XHTML 1.0 检查表
- 从 HTML 4.01 迁移到 XHTML
- 新旧写法对照
- XHTML 也要校验
- 浏览器按 HTML 处理 XHTML 的风险

### 第 8 章 CSS 入门

- CSS 规则的构成
- 选择器语法
- color 属性
- 合并多条规则
- border-bottom 与 underline 的区别
- 通用样式与个性样式
- 元素树与选择器
- 外部样式表
- link 标签引入样式
- 继承
- 不是全部属性都能继承

### 第 9 章 字体与颜色

- font-family 字体族
- 候选字体列表与兜底
- font-size 的取值
- px 百分比 em 与关键字
- font-weight 字重
- font-style 斜体
- 颜色三种指定方式
- 十六进制色码
- rgb 颜色
- text-decoration 文字装饰
- 去掉链接下划线

### 第 10 章 盒模型

- 盒模型四层构成
- padding 与 margin 的区别
- 背景延伸到 padding 不延伸到 margin
- padding margin 可选且独立
- width 与 height
- class 与 id 的适用场景
- id 命名规则
- id 选择器与限定选择器
- 多张样式表与覆盖顺序
- link 的 media 属性
- border-style 八种取值
- border-width 关键字与像素
- 分侧属性
- background-image 平铺
- background-repeat
- background-position
- 盒模型四层
- margin 与 padding 判据
- 背景色范围
- class 与 id 取舍
- 多张样式表顺序覆盖
- media 属性分流
- border-collapse

### 第 11 章 div 与 span

- div 与 span
- 页面逻辑分块
- 后代选择器
- span 的使用步骤
- a 元素的多种状态
- 伪类
- 层叠 cascade
- 特异性
- 属性回溯到不那么具体的规则

### 第 12 章 布局与定位

- 正常流
- 浮动前必须设宽度
- float 脱离正常流
- 内联内容绕开浮动元素
- 浮动元素不参与外边距折叠
- 两栏布局与 gutter 边距
- clear 属性
- 浮动对阅读顺序的影响
- 图片浮动让文字绕图
- liquid 布局
- frozen 布局
- jello 布局
- 绝对定位
- 绝对定位对流内元素不可见
- position 四值
- fixed 定位
- relative 定位
- z-index 层叠顺序
- 绝对定位与 clear 的冲突
- 三种布局方案取舍
- float 浮动
- clear
- 两栏布局
- position: absolute
- z-index
- liquid/frozen/jello 布局
- 流内与流外

### 第 13 章 表格与列表

- table tr th td 四件套
- 表格按行定义
- 空单元格也要写 td
- 表头放左边的写法
- summary 属性
- caption 表格标题
- 单元格无 margin
- border-spacing
- border-collapse
- 斑马纹交替行
- rowspan 跨行
- colspan 跨列
- 嵌套表
- table table th 后代选择器
- list-style-type
- 表格布局是过时做法
- table 结构
- tr/th/td
- caption 与 summary
- rowspan 合并
- 嵌套表格
- 斑马纹
- 文本对齐 class

### 第 14 章 XHTML 表单

- 表单的交互往返流程
- form 的 action 属性
- form 的 method 属性
- name 属性的胶水作用
- input 的 type
- radio 单选共享 name
- checkbox 多选
- checked 默认选中
- select 与 option
- option 不需要 name
- textarea 与 rows cols
- value 设置默认文字
- maxlength 限制
- POST 与 GET 的区别
- GET 的字符上限
- 表单排版用表格加 CSS

### 附录 十大未覆盖话题

- 更多选择器
- 框架
- 多媒体与 Flash
- 建站工具
- 客户端脚本
- 服务端脚本
- 搜索引擎优化
- 打印样式表
- 移动设备页面
- 博客

### 第 2 章 认识更多 HTML 元素

- a 元素与 href
- img 元素
- em 强调
- 页面内链接

### 第 4 章 链接与路径

- 相对路径
- ../ 父目录
- 多层目录互链
- 页内锚点跳转

### 第 6 章 严格 HTML 与标准

- doctype
- W3C 校验
- 编码声明

### 第 7 章 从 HTML 迁移到 XHTML

- XHTML 1.0 Strict
- 元素必须闭合
- 空元素自闭合
- 属性必须加引号
- 正确嵌套
- xmlns 与 xml:lang
- quirks mode

### 第 8 章 用 CSS 样式化

- 外部样式表
- link 元素
- CSS 选择器
- 合并选择器
- 样式继承
- 选择器与元素树映射

### 第 9 章 颜色与字体

- 字体栈
- font-size
- font-weight
- font-style
- 颜色名/十六进制/rgb
- border-bottom 做下划线

### 第 11 章 div、span 与层叠

- 层叠
- 特异性
- class 选择器
- id 选择器
- 后代选择器
- a:link 与 a:visited
- table table th

### 第 14 章 表单

- form 元素
- action 与 method
- GET 与 POST
- text 输入
- radio 单选
- checkbox 多选
- select 与 option
- textarea
- submit 提交
- name 与 value 对应
- checked 默认选中

## JavaScript DOM 和 AJAX 入门指南

### 第 0 章 简介

- JavaScript 简史
- Netscape 与 IE 浏览器竞争
- W3C DOM 与 ECMAScript 标准
- 结构表现行为三层分离
- 不引人注目的 JavaScript

### 第 1 章 JavaScript 入门

- script 标签
- HTML 注释包裹脚本
- 单行与多行注释
- 代码块
- 语句结束符
- 脚本执行顺序
- 函数与调用时机
- 对象属性与方法
- 事件
- 宿主对象
- document.write 换样式表
- screen.availWidth

### 第 2 章 数据和决策

- 基本数据类型
- null 与 undefined
- 字符串转义序列
- 运算符与优先级
- 字符串拼接
- var 变量声明
- 驼峰命名
- prompt 返回字符串
- Number 转换
- parseFloat 与 parseInt
- NaN
- typeof
- String 对象方法
- indexOf
- substring
- Date 对象
- 月份从 0 开始
- Math 对象
- Math.random
- 数组创建
- 数组方法 slice
- 数组方法 concat
- join 与 split
- sort 排序
- reverse
- 比较运算符
- 逻辑运算符
- if else if
- switch 与 break 贯穿
- for 循环
- for..in
- while 循环
- do..while
- break 与 continue

### 第 6 章 核心 API 速查

- getElementById
- getElementsByTagName
- getElementsByClassName
- document.images
- document.forms 与 form.elements
- document.body
- createElement
- createTextNode
- appendChild
- insertBefore
- removeChild
- replaceChild
- cloneNode
- hasChildNodes
- parentNode
- childNodes
- firstChild 与 lastChild
- previousSibling 与 nextSibling
- nodeType
- nodeName
- nodeValue
- getAttribute 与 setAttribute
- className
- classList
- style 属性
- innerHTML
- id 属性
- focus 与 blur
- disabled
- offset 尺寸与位置
- href/src/alt/title 属性
- htmlFor
- window.onload
- DOMContentLoaded
- onreadystatechange 与 readyState
- DOM0 事件绑定
- addEventListener
- attachEvent
- event.target 与 srcElement
- event.type
- event.button
- event.keyCode
- 修饰键状态
- stopPropagation 与 cancelBubble
- preventDefault 与 returnValue
- return false
- onsubmit 表单校验
- form.submit()
- input 控件属性
- select.options 与 selectedIndex
- validity.valid
- HTML5 约束属性
- novalidate
- 表单 CSS 伪类
- isNaN
- Number/parseFloat/parseInt
- typeof
- 字符串方法
- 数组方法
- Math 舍入与随机
- Date 方法
- Image 对象预加载
- setTimeout 与 clearTimeout
- setInterval 与 clearInterval
- window.open
- window.close
- window.opener
- 窗口移动与导航方法
- 滚动位置读取
- backgroundPosition
- XMLHttpRequest
- ActiveXObject
- xhr.open
- xhr.send
- setRequestHeader
- readyState
- onreadystatechange
- xhr.status
- responseText 与 responseXML
- xhr.abort
- JSON.parse
- eval
- encodeURI
- RegExp 对象
- regex.test 与 exec
- 正则字符串方法
- HTML5 属性特性检测
- 滚动容器
- location 目录前缀
- console.log
- try/catch

### 第 7 章 可复用代码模板

- 独立脚本骨架（结构/行为分离）
- 多前缀能力检测
- DOM 能力门
- 按类名批量挂行为
- 默认参数兜底
- 对象字面量命名空间
- DOMContentLoaded 就绪读取
- 首末兄弟元素过滤文本节点
- CSS-DOM 类名切换
- cssjs 四动作
- addEvent 兼容分流
- 事件目标三级兼容
- stopBubble / stopDefault 封装
- 折叠显隐内容块
- 多列等高修复
- 悬停切类（this 传参）
- 事件委托
- 图片预加载
- 老式 name 翻转
- 自动翻转
- 父元素翻转
- 嵌入式幻灯片
- 动态幻灯片
- 一次性超时警告
- 自动播放幻灯片
- 弹窗链接
- 分层广告覆盖层
- 图片浮层定位
- 图片画廊容器与翻页
- HTML5 特性检测
- 失焦即时校验
- 无效字段汇总列出
- 双字段一致性校验
- XHR 兼容获取
- GET 请求骨架
- responseText 与 responseXML 渲染
- JSON 解析渲染
- POST 请求组装
- XHR 超时兜底
- 跨域内容代理
- HIJAX 可选增强
- 正则校验邮箱
- 调试三件套（try/catch、括号自检）
- 表单控件遍历
- 复选框全选反选
- 选择框取值
- 选择框增删改插
- 提交时禁用提交按钮
- 依赖字段显隐切换
- 长表格分页
- API 频次统计画像
- DOMhelp 库定义体
- 原书代码 bug 负样本

### 第 8 章 兼容性与渐进增强

- 渐进增强总顺序
- 无脚本可访问性判据
- 图库 href 直指大图
- document.write 局限
- NOSCRIPT 弃用
- 对象检测取代浏览器探测
- navigator.appName 不可信
- HTML5 属性 in 检测
- DOM 能力门的历史定位
- 事件模型三级分流
- 事件目标兼容获取
- stopPropagation 兼容
- preventDefault 兼容
- window.event 老 IE
- Safari 文本节点 bug
- Safari preventDefault 聚焦 bug
- IE 动态建表 tbody 坑
- send(null) 兼容
- readyState 只比较 1 和 4
- Safari 缓存响应绕过
- nodeName 大小写归一
- 滚动位置三级检测
- for/class 属性名差异
- 循环删除元素索引错位
- parentNode 上溯终止条件
- Ajax 失败放行链接
- 表单验证三层降级
- 第三方内容静态降级
- 服务端验证总后备
- 渐进增强仍成立
- 老 IE 兼容层可弃

### 第 9 章 局限与坑

- 时代坐标
- document.write 的废弃
- 浏览器嗅探与特性检测
- 行内事件属性
- addEventListener
- document.all 废弃
- attachEvent 兼容写法
- ActiveXObject 与 XMLHttpRequest
- window.open 弹窗
- setInterval 逐帧动画
- requestAnimationFrame
- offsetLeft 手算定位
- getBoundingClientRect
- alert 调试
- eval 与 JSON.parse
- innerHTML 字符串注入
- Cache-Control 与 ETag
- XHR 超时处理
- 正则校验邮箱
- JavaScript 密码保护
- prompt 与假保护
- jQuery ready 与 toggle
- Bootstrap 2 旧写法
- Google Maps 旧接口
- noscript 与 javascript 伪协议
- 全局变量与严格模式
- querySelector 缺失
- classList 缺失
- dataset 与 fetch 缺失
- ES6 语法缺失
- 约束验证 API 缺失
- 构建工具缺失
- 源材料缺陷

### 第 10 章 费曼自检

- DOM 树
- 事件目标
- 事件对象
- addEventListener 挂接
- 事件冒泡
- 事件委托
- stopPropagation
- preventDefault
- return false 差异
- 修改 DOM 节点
- 脚本执行时机
- DOMContentLoaded
- onreadystatechange
- this 指向

### 第 11 章 练习路线

- 语言底子练习
- DOM 与三层分离
- 事件与 CSS-DOM
- 图片库案例改进
- 动画与表单增强
- 表单验证
- XHR 五步
- HIJAX 渐进增强
- 调试与断点
- 练习纪律
- 能力检测
- 渐进增强验收

### 附录 覆盖与未覆盖

- 覆盖范围
- 未取到证据
- 题名偏差

## JavaScript DOM 编程艺术（第 2 版）

### Chapter 1. A Brief History of JavaScript

- JavaScript 起源
- 浏览器大战
- DHTML 之痛
- DOM 的由来
- DOM 是通用 API

### Chapter 2. JavaScript Syntax

- 语句与注释
- 变量与数据类型
- 数组
- 对象
- 运算符
- 条件语句
- 循环
- 函数
- 作用域
- 原生对象与宿主对象

### Chapter 3. The Document Object Model

- 节点树
- 家族关系术语
- 元素/属性/文本节点
- nodeType
- childNodes 与空白节点
- class 与 id
- getElementById
- getElementsByTagName 通配符
- getElementsByClassName
- getAttribute
- setAttribute
- DOM 双向通道
- DOM 更新不反映到查看源代码

### Chapter 4. A JavaScript Image Gallery

- 单页图片库实战
- 事件处理器
- return false 取消默认行为
- childNodes
- nodeType
- nodeValue
- firstChild 与 lastChild

### Chapter 5. Best Practices

- 优雅降级
- 渐进增强
- 不唐突的 JavaScript
- 三层分离
- 向后兼容
- 对象检测
- 浏览器嗅探
- 搜索引擎爬虫即关 JS 访客
- 减少 DOM 访问
- 脚本置底部
- 合并脚本
- minification 压缩

### Chapter 6. The Image Gallery Revisited

- 代码检查点
- addLoadEvent 加载队列
- 避免 onkeypress
- onclick 支持键盘访问
- id 钩子共用
- 勿做无谓假设
- DOM Core 与 HTML-DOM

### Chapter 7. Creating Markup on the Fly

- document.write 的问题
- innerHTML
- createElement
- createTextNode
- appendChild
- insertBefore
- 自写 insertAfter
- 先造后插
- XMLHttpRequest
- readyState 与 onreadystatechange
- 同源限制
- Hijax

### Chapter 8. Enhancing Content

- 重要内容不用 DOM 造
- DOM 二次呈现
- displayAbbreviations
- displayCitations
- displayAccesskeys
- IE6 的 abbr 问题

### Chapter 9. CSS-DOM

- style 只读内联样式
- camelCase 属性名
- style 读写 vs 节点关系只读
- 何时该用 CSS
- className 覆盖问题
- 追加 class 拼接空格
- style 与 hover 的层归属

### Chapter 10. An Animated Slideshow

- 动画三要素
- moveElement 抽象
- setTimeout 递归补间
- 作用域陷阱与自建元素属性
- 缓动
- 安全检查
- DOM 生成滑窗标记

### Chapter 11. HTML5

- HTML5 是技术集合
- Modernizr 特性检测
- 新元素 display:block 回退
- IE createElement 识别新元素
- 新 input 类型回退
- video 多格式 source
- canvas 与音视频
- 特性检测决定回退脚本

### Chapter 12. Putting It All Together

- 全流程实战站点
- 导航高亮
- 表单增强
- Ajax 表单提交
- 脚本压缩

### Appendix A. DOM Scripting Libraries

- 库的取舍标准
- jQuery/Prototype/YUI/Dojo/MooTools
- CDN 与失败回退
- 库写法对照

### 第 1 章 JavaScript 简史

- JavaScript 诞生与标准化
- DOM Level 0
- 浏览器大战
- DHTML 争议
- DOM Level 1
- DOM scripting

### 第 2 章 JavaScript 语法

- 脚本位置
- 解释型语言
- 语句与注释
- 变量声明
- 弱类型
- 数据类型
- 数组
- 关联数组风险
- 对象字面量
- 对象分类
- 运算符与流程控制
- 函数
- 变量作用域
- script 标签放 body 末尾
- 外部脚本文件

### 第 3 章 文档对象模型

- DOM 含义
- 节点树
- 节点类型
- CSS 钩子
- getElementById
- getElementsByTagName
- getElementsByClassName
- getAttribute
- setAttribute
- DOM 动态更新

### 第 4 章 JavaScript 图片库

- 图片库问题
- 列表与占位图
- showPic
- HTML-DOM 属性
- onclick 事件
- return false 取消默认
- childNodes
- nodeType
- nodeValue
- firstChild 与 lastChild
- CSS 配合

### 第 5 章 最佳实践

- 可访问性
- 优雅降级
- 渐进增强
- 不唐突 JavaScript
- 对象检测
- 浏览器嗅探弊端
- DOM 访问优化
- 脚本位置优化
- 脚本压缩
- window.open 注意

### 第 6 章 图片库重构

- 降级检查
- 不唐突检查
- imagegallery 钩子
- prepareGallery
- addLoadEvent
- 防御性检查
- onclick 与 onkeypress
- DOM Core
- HTML-DOM
- 结构与行为分离

### 第 7 章 动态创建标记

- document.write
- innerHTML
- createElement
- createTextNode
- appendChild
- insertBefore
- insertAfter
- preparePlaceholder
- Ajax
- XMLHttpRequest
- readyState
- 同源策略
- Hijax
- addLoadEvent 加载队列
- createElement 创建元素
- createTextNode 创建文本
- appendChild 插入节点
- 嵌套标记构建
- getHTTPObject 跨浏览器 XHR
- Ajax 拉取并插入内容
- createElement 与 createTextNode
- document fragment
- appendChild 与 insertBefore
- insertAfter 自定义函数
- innerHTML 的局限
- document.write 的局限
- XMLHttpRequest 同源策略
- Ajax 破坏后退键
- onreadystatechange 异步时序

### 第 8 章 内容增强

- 增强而非创造
- 语义标记
- abbr 与 acronym
- DOCTYPE
- displayAbbreviations
- lastChild 技巧
- IE6 兼容
- displayCitations
- displayAccesskeys
- 自动目录

### 第 9 章 CSS-DOM

- 三层分离
- style 对象
- camelCase 属性
- 内联样式限制
- DOM 写样式场景
- getNextElement
- 表格斑马纹
- 事件响应样式
- className
- addClass
- 抽象函数
- style 属性读写
- camelCase 命名
- addClass 安全追加类
- className 分离表现
- getNextElement 找下一元素节点
- styleHeaderSiblings
- styleElementSiblings 抽象
- stripeTables 斑马纹
- highlightRows 悬停高亮
- style 对象只读内联样式
- style.fontFamily 驼峰命名
- className 优于直接改样式
- addClass 函数
- oldClassName 快照恢复
- getNextElement 跳过空白文本节点
- parseInt 解析位置

### 第 10 章 动画幻灯片

- 动画定义
- position 与容器
- setTimeout
- clearTimeout
- parseInt
- 增量移动
- moveElement
- 字符串拼接
- overflow 裁剪
- 作用域陷阱
- 元素自定义属性
- 缓动
- Math.ceil
- 安全检查
- 动态生成标记

### 第 11 章 HTML5

- HTML5 集合
- 四层模型
- 新元素与 API
- 渐进增强
- Modernizr
- 新元素兼容
- canvas
- getImageData
- audio 与 video
- 多 source
- source 顺序
- video DOM 属性
- 自定义控件
- addEventListener
- 新增 input 类型
- 新增表单属性
- 向后兼容问题
- inputSupportsType 特性检测
- placeholder 回退实现
- Web Storage
- Web Sockets
- Web Workers
- 拖放 API
- 地理定位
- video 多 source 标记
- 自定义视频控件
- play/pause 按钮
- video 事件监听
- HTML5 video 多 source 回退
- canvas 像素操作 getImageData
- canvas 灰度化算法
- canvas 同域限制
- Modernizr 特性检测
- inputSupportsType 输入类型检测
- placeholder 回退
- Modernizr 加载位置
- addEventListener 与 attachEvent 兼容

### 第 12 章 综合示例（Putting It All Together）

- 站点结构设计
- CSS 拆分与 @import
- 颜色与背景同时设置
- CSS Reset
- global.js 组织
- highlightPage 页面高亮
- body id 扩展技巧
- 首页轮播实现
- prepareInternalnav 站内导航
- split 提取锚点 id
- 自定义属性解决作用域
- 图片库复用
- stripeTables 斑马纹
- oldClassName 快照技巧
- label 聚焦回退
- Form 对象与 elements
- placeholder 回退（resetFields）
- 表单校验三铁律
- isFilled 与 isEmail
- onsubmit 拦截提交
- Hijax 渐进提交
- encodeURIComponent URL 编码
- POST Content-type 请求头
- 正则提取响应片段
- match 捕获组
- JavaScript 压缩
- 优雅降级原则

### 附录 A DOM 脚本库

- 库的价值与代价
- 选择库的七个问题
- 主流库简介
- CDN 与本地回退
- $() 选择器
- 链式调用
- each 迭代
- CSS 选择器
- 属性选择器
- 伪类选择器
- jQuery 特有选择器
- 回调过滤
- jQuery 创建与移动元素
- clone 复制元素
- ready 文档就绪
- click 绑定与触发
- Prototype Ajax 三件套
- jQuery Ajax 方法
- 定时自动保存
- 动画库（Moo.fx 与 Script.aculo.us）
- jQuery animate 与 easing
- 内置动画效果
- 克制的使用效果

### 第 3 章 DOM 初探

- getElementsByClassName 兼容写法

### 第 5 章 JavaScript 编程

- 对象检测
- window.open 与 popUp 封装
- 降级版链接
- 不唐突事件绑定
- return false 拦截默认行为

### 第 6 章 案例研究：图片库

- 缩略图列表标记
- class 与 id 钩子

### 第 8 章 充实文档内容

- displayAbbreviations 缩写表
- displayAccesskeys 快捷键列表
- abbr 的 title 与文本收集
- lastChild 取值
- 关联数组与 for/in
- dl/dt/dd 定义列表
- IE 兼容补丁

### 第 10 章 动画效果

- setTimeout 递归动画
- 等距移动原理
- moveElement 位置补间
- clearTimeout 防动画堆积
- Math.ceil 缓动步进
- parseInt 解析坐标
- positionMessage 启动动画
- prepareSlideshow 滑窗轮播
- overflow 视窗
- z-index 遮罩

### 第 12 章 综合案例

- 图片库整合（showPic/preparePlaceholder/prepareGallery）
- highlightPage 当前页高亮
- body 挂 id
- showSection 站内锚点导航
- 自定义属性传递参数
- focusLabels 标签聚焦
- placeholder 的 JS 回退
- 表单校验 isFilled/isEmail
- displayAjaxLoading 加载提示
- submitFormWithAjax Hijax 提交
- Hijax 三段式决策
- encodeURIComponent 编码表单数据
- 正则提取响应内容
- stripeTables className 版
- highlightRows 高亮还原

### 附录 A JavaScript 库

- jQuery 选择器简化 DOM 操作
- each 遍历
- 链式调用
- animate 补间动画
- CDN 加载与本地回退
- load 方法 Ajax
- 选库标准
- 先理解原理再用库

### 第 5 章 JavaScript 编程最佳实践

- 对象检测
- 对象检测不带括号
- 浏览器嗅探的弊端
- 减少 DOM 访问
- 减少标记量
- 脚本放文档末尾
- 合并脚本文件
- 脚本压缩 JSMin
- YUI Compressor
- Closure Compiler

### 第 4 章 案例研究：JavaScript 图片库

- 优雅降级 href 真实地址
- 弹窗链接回退
- 禁止自动生成的核心内容
- Hijax 渐进增强

### 第 6 章 案例研究：JavaScript 图片库改进版

- 元素存在性检测
- 事件处理函数返回 false
- addLoadEvent 解决 onload 覆盖

### 第 8 章 充实文档的内容

- displayAbbreviations 缩写词列表
- lastChild 与 firstChild 的坑
- IE6 abbr 兼容
- displayAccesskeys 快捷键列表
- blockquote cite 展示
- DOM 生成增强元素以便降级

### 第 10 章 用 JavaScript 实现动画效果

- moveElement 移动函数
- setTimeout 递归动画
- 缓动算法十分之一距离
- Math.ceil 与 Math.floor 的坑
- 定时器 ID 挂元素属性
- overflow hidden 视窗技巧
- DOM 生成轮播元素
- 安全网替代显式初始化
- 用户控制权与 WCAG

### 第 12 章 综合示例

- CSS 文件拆分与 import
- highlightPage 高亮当前导航
- showSection tab 导航
- 表单 focusLabels
- resetFields 占位回退
- 客户端校验不能替代服务端
- submitFormWithAjax
- HTML5 新元素 IE 兼容
- display block 兼容旧浏览器
- 脚本压缩实测
- stripeTables 斑马纹

### 第 3 章 DOM

- 节点树模型
- getElementById
- getElementsByTagName
- getElementsByClassName
- getAttribute 与 setAttribute
- nodeType 节点类型
- childNodes 含空白文本节点
- firstChild 与 nodeValue
- parentNode 与 nextSibling
- document.getElementsByTagName 活集合

## Python 编程：从入门到实践（第 3 版）

### 第 1 章 开始起步

- 安装 Python
- 安装 VS Code
- 运行 hello_world.py
- 在终端运行 Python
- Python 版本要求
- 常见故障排查

### 第 2 章 变量和简单数据类型

- 变量即标签
- 字符串方法
- removeprefix()
- f-string
- 整数与浮点数
- 注释
- Python 之禅

### 第 3 章 列表简介

- 列表定义
- 索引从 0 开始
- append()
- insert()
- del
- pop()
- remove()
- sort()
- sorted()
- len()
- 避免索引错误
- 索引与负索引
- del 与 pop 的选择
- sort 与 sorted
- IndexError

### 第 4 章 操作列表

- for 循环
- 缩进错误
- range()
- 列表推导式
- 切片
- 复制列表
- 元组
- PEP 8 风格
- 列表拷贝陷阱

### 第 5 章 if 语句

- 条件测试
- 检查相等与不等
- 数值比较
- 检查多个条件
- in 与 not in
- 布尔表达式
- if-elif-else
- 省略 else
- 多个独立 if
- 检查列表非空
- 条件测试与布尔值
- 相等与不等比较
- 大小写敏感的相等测试
- 数值比较运算符
- and 与 or 逻辑运算
- in 与 not in 检查
- 布尔表达式跟踪状态
- if-elif-else 只执行一个分支
- if-else 重构技巧
- 用 elif 替代 else
- 多个独立 if 分支
- 空列表为 False
- 比较运算符空格风格
- if-elif-else 分支
- 布尔测试
- else 兜底与数据脏值

### 第 6 章 字典

- 键值对
- 访问值
- 添加键值对
- 修改值
- 删除键值对
- get()
- 遍历键值对
- 遍历键
- 遍历值
- 嵌套
- 字典列表
- 字典中嵌套字典
- 字典定义与键值对
- 访问字典值
- KeyError 异常
- 增改删键值对
- get() 与默认值
- items() 遍历键值对
- keys() 遍历键
- values() 遍历值
- sorted() 排序遍历结果
- set() 值去重
- 字典列表嵌套
- 字典中的列表
- 字典中的字典
- 嵌套结构一致性
- items 与 keys 与 values 遍历
- get 避免 KeyError
- 字典嵌套三形态

### 第 7 章 用户输入和 while 循环

- input()
- 清晰提示
- int() 转换
- 取模运算符
- while 循环
- 标志位
- break
- continue
- 避免死循环
- 列表间移动元素
- 用 while 填充字典
- input() 接收输入
- 提示语末尾留空格
- 多行提示拼接
- input() 返回字符串
- int() 类型转换
- TypeError 字符串与整数比较
- 取模运算符 % 判偶数
- while 循环与死循环
- Ctrl+C 终止循环
- while 循环退出条件
- 标志变量
- break 退出循环
- continue 跳过本次循环
- for 循环中不修改列表
- while 搬运列表元素
- while 删除所有匹配值
- while 填充字典
- input 返回字符串
- int 类型转换
- 死循环与 CTRL-C

### 第 8 章 函数

- 定义函数
- 形参与实参
- 位置实参
- 关键字实参
- 默认值
- 返回值
- 传递列表
- 禁止函数修改列表
- *args
- **kwargs
- 导入模块
- 函数别名
- 函数定义与调用
- docstring 文档字符串
- 位置参数顺序问题
- 关键字参数
- 参数默认值
- 默认值参数位置
- return 返回值
- 返回字典
- 可选参数
- 向函数传列表
- 传递切片保护原列表
- *args 任意数量参数
- *args 位置
- **kwargs 任意关键字参数
- import 导入模块
- from-import 导入函数
- import as 别名
- import * 不推荐
- 函数命名风格
- 位置参数顺序陷阱
- 默认参数顺序
- 函数返回 None
- 传列表与切片保护
- 可变默认参数陷阱
- *args 与 **kwargs

### 第 9 章 类

- 创建类
- __init__()
- self
- 实例属性
- 方法调用
- 修改属性
- 继承
- super()
- 重写父类方法
- 实例作属性
- 导入类
- Python 标准库
- 类命名风格
- class 定义类
- __init__ 构造器
- self 参数
- 实例化对象
- 访问属性与调用方法
- 默认属性值
- 直接修改属性
- 通过方法修改属性
- 通过方法递增属性
- 方法中的数据校验
- super() 调用父类构造器
- 父类定义顺序
- 子类重写方法
- 组合：实例作为属性
- 导入多个类
- 模块导入模块
- 标准库 random 模块
- random 不用于安全场景
- 类命名 CamelCase
- 类与模块导入风格
- __init__ 与 self
- 继承与 super
- 组合
- 类命名约定

### 第 10 章 文件和异常

- pathlib.Path
- read_text()
- 相对路径与绝对路径
- splitlines()
- ZeroDivisionError
- try-except-else
- FileNotFoundError
- pass 静默失败
- json.dumps()
- json.loads()
- path.exists()
- 重构
- pathlib 读写文件
- json 存取数据
- 函数重构

### 第 11 章 测试代码

- pip
- 安装 pytest
- 单元测试
- 测试用例
- 测试通过
- 测试失败
- 响应失败测试
- assert 断言
- 类测试
- fixture
- test_ 命名约定
- --user 安装

### 第 12 章 发射子弹的飞船

- Pygame 安装
- 游戏窗口
- 事件循环
- Clock.tick(60)
- Settings 类
- 加载飞船图像
- rect 矩形
- _check_events()
- _update_screen()
- 连续移动
- 边界限制
- 全屏模式
- Bullet 类
- Sprite 与 Group
- blit()

### 第 13 章 外星人！

- Alien 类
- _create_fleet()
- 创建整行外星人
- 边缘检测
- 舰队下沉反向
- sprite.groupcollide()
- 子弹-外星人碰撞
- 补充舰队
- 外星人撞船
- 屏幕底部判负
- Game Over
- game_active

### 第 14 章 计分

- Button 类
- Play 按钮
- 游戏激活状态
- 重置游戏
- 隐藏鼠标指针
- 升级速度设置
- Scoreboard
- 递增分值
- 分数取整
- 最高分
- 显示等级
- 显示剩余船只

### 第 15 章 生成数据

- 安装 Matplotlib
- subplots()
- plot()
- scatter()
- 标题与坐标轴
- 刻度设置
- 内置样式
- 自定义颜色
- colormap
- savefig()
- RandomWalk 类
- random.choice()
- figsize 与 dpi
- 隐藏坐标轴
- Plotly Express
- Die 类
- 直方图
- 双骰分布
- write_html()
- matplotlib 样式
- seaborn 样式已移除的修复
- savefig 保存图表

### 第 16 章 下载数据

- CSV 格式
- csv.reader()
- enumerate()
- 表头解析
- 提取最高温
- datetime.strptime()
- 日期轴
- autofmt_xdate()
- 高低温双序列
- fill_between()
- alpha 透明度
- 缺失数据处理
- GeoJSON
- json.dumps(indent=4)
- features 列表
- 提取震级与经纬度
- px.scatter_geo()
- size 映射
- color_continuous_scale
- hover_name
- CSV 数据绘制
- strptime 日期格式
- 双序列与阴影填充
- 配套数据文件

### 第 17 章 使用 API

- API 概念
- GitHub API URL
- 安装 Requests
- requests.get()
- status_code
- r.json()
- 遍历 items
- 速率限制
- px.bar()
- update_layout()
- hover_name
- 自定义 tooltip
- 可点击链接
- update_traces()
- Hacker News API
- topstories.json
- itemgetter 排序
- GitHub API 请求头
- status_code 状态码
- json() 解析响应
- 仓库数据提取
- Plotly 条形图
- hover 悬停文本
- HN 批量 API 调用
- GitHub API 调用
- 速率限制与 token
- 请求头媒体类型
- Hacker News descendants 字段缺失

### 第 18 章 Django 入门

- 编写规格说明
- python -m venv
- 虚拟环境
- 安装 Django
- django-admin startproject
- migrate
- runserver
- startapp
- 定义模型
- CharField
- DateTimeField
- TextField
- ForeignKey
- on_delete=CASCADE
- Meta 类
- makemigrations
- createsuperuser
- admin.site.register()
- Django shell
- entry_set.all()
- 项目级 urls.py
- 应用级 urls.py
- app_name
- 视图函数
- 模板
- base.html
- 模板继承
- {% url %}
- {% for %}
- {% empty %}
- {{ }}
- date 过滤器
- linebreaks 过滤器
- startproject 末尾的点
- 模型与迁移
- admin 站点
- URL 视图 模板链路

### 第 19 章 用户账户

- forms.py
- ModelForm
- Meta.model
- Meta.fields
- Meta.labels
- new_topic
- GET 与 POST
- new_entry
- edit_entry
- accounts 应用
- 登录页
- 登出
- 注册页
- LOGIN_REDIRECT_URL
- LOGOUT_REDIRECT_URL
- @login_required
- ForeignKey(User)
- 数据归属用户
- 迁移旧数据
- 保护 edit_entry
- 新主题关联当前用户
- 用户账号系统
- login_required 装饰器
- 框架默认安全

### 第 20 章 设置样式并部署应用

- django-bootstrap5
- 改造 base.html
- 导航栏
- 账号链接
- 登出表单
- jumbotron 首页
- pip freeze
- requirements.txt
- requirements_remote.txt
- gunicorn
- psycopg2
- .platform.app.yaml
- relationships
- web.commands.start
- disk
- mounts
- hooks.build
- hooks.deploy
- .platform/routes.yaml
- .platform/services.yaml
- postgresql:12
- settings.py 平台配置
- config.is_valid_platform()
- ALLOWED_HOSTS
- SECRET_KEY
- Postgres 凭据
- Git 提交
- 推送部署
- 自定义错误页
- 删除项目

### 附录 A 安装与故障排除

- Windows 的 py 启动器
- 重跑安装器
- macOS Apple 版 Python
- 检查 Python 版本
- Python 关键字
- Python 内置函数

### 附录 B 文本编辑器和 IDE

- VS Code 配置
- Tab 与空格
- 配色主题
- 行长指示
- 简化输出
- 块缩进快捷键
- 块注释快捷键
- 移动行快捷键
- IDLE
- Geany
- Sublime Text
- Emacs 与 Vim
- PyCharm
- Jupyter

### 附录 C 获取帮助

- 求助顺序
- 重试与暂停
- 本书在线资源
- 在线搜索
- Stack Overflow
- 官方 Python 文档
- 库文档
- r/learnpython
- 博客
- Discord
- Slack

### 附录 D 使用 Git 进行版本控制

- 安装 Git
- 配置 Git
- 创建项目
- .gitignore
- git init
- git status
- git add
- git commit
- git log
- 第二次提交
- 放弃更改
- 检出历史提交
- 删除仓库

### 附录 E 部署故障排除

- 理解部署
- 照屏幕建议排错
- 读取日志输出
- Windows 排错
- WSL
- Git Bash
- macOS 排错
- Linux 排错
- 其他部署方式

### 6.1 起步与环境

- 第一个程序 print
- 终端运行脚本
- 交互式解释器
- pip 安装包

### 6.2 变量、字符串、数字

- 变量与重赋值
- NameError
- upper() 与 lower()
- f-string
- 制表符与换行符
- strip/lstrip/rstrip
- removeprefix() 去前缀
- 整数与浮点数
- 乘方运算
- 下划线分隔大数
- 多重赋值
- 常量
- 注释
- Python 之禅

### 6.3 列表与元组

- 列表索引与负索引
- 修改元素
- append()
- insert()
- del 语句
- pop() 弹出
- remove() 按值删除
- 空列表动态构建
- sort() 排序
- for 循环
- range() 函数
- 列表推导式
- 切片
- 切片拷贝
- 元组
- 元组不可修改
- 单元素元组尾逗号

### 6.4 条件与循环

- if-else 语句
- 大小写不敏感比较
- if-elif-else 链
- elif 替代 else
- 多个独立 if
- 判空列表
- input() 函数
- int() 类型转换
- 取模运算判奇偶
- 标志变量
- break 语句
- continue 语句
- while 循环操作列表
- while 删除全部特定值

### 6.5 字典

- 字典基础
- 键值对访问
- items() 遍历
- keys() 遍历
- values() 遍历
- 字典列表
- 列表作为字典值
- 字典嵌套字典

### 6.6 函数

- def 定义函数
- 函数调用
- 位置实参
- 关键字实参
- 参数默认值
- 返回字典
- 函数修改列表
- 传切片保护列表
- *toppings 任意数量参数
- 导入整个模块
- 导入单个函数
- 函数别名
- 模块别名
- 导入所有函数

### 6.7 类与继承

- class 定义类
- __init__() 方法
- self 参数
- 实例属性
- 属性校验
- 继承
- super() 调用父类
- 子类新增属性
- 重写父类方法
- 组合拆分独立类
- 导入类
- random 标准库

### 6.8 文件、异常、JSON、测试

- pathlib 读取文件
- read_text() 与 rstrip()
- splitlines() 逐行读取
- 文件路径
- utf-8 编码读取
- try-except-else
- ZeroDivisionError
- FileNotFoundError
- pass 沉默失败
- json.dumps() 写入
- json.loads() 读取
- 记住用户数据重构
- pytest 编写测试
- assert 断言
- 可选参数修测试
- 运行 pytest

### 6.9 项目一：Pygame

- 游戏主类骨架
- 游戏主循环
- Settings 设置类
- Ship 类
- rect 定位
- 亚像素位置 float
- 移动标志
- 边界限制
- KEYDOWN 事件
- KEYUP 事件
- 退出游戏
- Bullet 类
- Sprite 精灵
- 精灵组更新
- 绘制子弹
- 屏幕刷新 flip()

### 6.10 项目二：数据可视化与 API

- Matplotlib 折线图
- set_title 与坐标轴标签
- tick_params
- scatter 散点图
- colormap 颜色映射
- axis 坐标范围
- savefig 保存图片
- RandomWalk 类
- choice 随机选择
- 随机游走可视化
- 起终点标记
- 隐藏坐标轴
- Plotly Express 直方图
- Die 类掷骰子
- 频率统计
- update_layout 刻度设置
- csv 模块解析
- strptime 日期解析
- 双序列绘图
- fill_between 区域填充
- autofmt_xdate 日期标签
- 缺失数据处理
- GeoJSON 解析
- scatter_geo 地图散点
- 色阶 color_continuous_scale

### 第 18 章 入门 Django

- 虚拟环境
- 激活虚拟环境
- django-admin 建项目
- migrate 迁移
- startapp 建应用
- INSTALLED_APPS 注册应用
- Topic 模型
- Entry 模型
- 外键与级联删除
- Meta 类
- __str__ 方法
- 注册 admin
- Django shell
- QuerySet 查询
- 项目级 URL 配置
- 应用级 URL 配置
- render 视图
- 模板上下文 context
- 模板继承
- 模板标签
- 模板变量
- for 与 empty 标签
- date 过滤器
- linebreaks 过滤器
- ModelForm

### 第 20 章 设计并部署 Django 应用

- pip freeze 生成依赖文件
- requirements.txt
- Platform.sh 配置
- YAML 配置文件
- 挂载 mounts
- 部署钩子 hooks
- 路由 routes
- settings.py 平台设置
- ALLOWED_HOSTS
- STATIC_ROOT
- DATABASES 配置
- git 初始化与提交
- .gitignore
- gunicorn 生产服务器

### 第 1 章 起步

- 环境搭建
- 运行第一个 Python 程序

### 第 2 章 变量和简单的数据类型

- 变量是标签不是盒子
- f-string
- strip 方法不改原字符串
- removeprefix 与 removesuffix
- 浮点数精度问题

### 第 11 章 测试

- pytest 与 test 前缀
- 断言
- 测试失败改代码不改测试

### 第 12 章 外星人入侵（Pygame）

- pygame 事件处理
- 飞船移动与开火
- 全屏设置
- 配套资源 ship.bmp

### 第 13 章 外星人

- Pygame 项目扩展

### 第 14 章 记分

- Pygame 项目扩展

### 第 20 章 部署

- Platform.sh 部署
- services.yaml 服务版本
- ALLOWED_HOSTS
- settings.py 中的 Path

### 附录

- Git 版本控制

## 算法竞赛入门经典（第 2 版）

### 第 1 章 程序设计入门

- 三步曲
- 算术表达式
- 整数除法
- 变量与输入
- scanf 取地址符
- 顺序结构
- 分支结构
- 逻辑运算符短路
- else if 链
- 赋值是动作
- 浮点误差
- 完全平方判定
- 整数溢出
- 数据类型边界
- 输出格式
- 样例通过不等于正确
- 实数输入输出
- 常量定义
- 整数拆位
- 前导零输出
- 交换变量
- 条件判断
- 逻辑短路

### 第 2 章 循环结构程序设计

- for 循环
- while 循环
- do-while 循环
- 计数器与累加器
- 循环的代价
- 双重循环复杂度
- 计时函数 clock
- 输出中间结果调试
- 重定向
- fopen
- 条件编译
- 多组数据重置
- min/max 初始化
- 变量屏蔽
- long long 输出格式
- 嵌套枚举
- 完全平方判定
- long long 防溢出
- do-while 语义
- 每步取模
- clock 计时
- scanf 返回值
- 多组数据输入
- 重定向输入输出
- fopen 文件读写

### 第 3 章 数组和字符串

- 一维数组
- 二维数组
- 大数组声明位置
- 数组整体赋值
- 字符数组
- 字符串结束符
- scanf 读字符串
- fgets
- gets 缓冲区溢出
- 常量数组
- n++ 与 ++n
- 自增滥用
- 进位制
- 整数表示
- 打表
- 黑盒测试
- 在线评测
- getchar 逐字符读取
- 标志变量翻转
- 常量数组查表
- 回文判定
- 镜像串判定
- 计数数组
- 预处理打表
- 字典序比较
- 环状序列
- 字符串解析
- 周期串
- 二维网格模拟
- 模拟长除
- 余数判重求循环节
- 双指针子序列匹配

### 第 4 章 函数和递归

- 自定义函数
- 结构体
- 形参与实参
- 值传递
- 指针作参数
- 数组作参数
- sizeof 形参数组
- 函数指针
- 调用栈
- 递归定义
- 递归终止条件
- 递归过深
- 栈溢出
- 段错误
- 中间结果溢出
- 返回局部变量地址
- 函数副作用
- 浮点递减循环
- 素数判定
- 栈大小调整
- 递归求阶乘
- 组合数约分防溢出
- 自顶向下逐步求精
- 全局状态重置
- 环形下标
- 二维表编码
- 跨行读取
- 结构体数组
- 浮点 EPS 比较
- 位运算求掩码
- 前缀匹配

### 第 5 章 C＋＋与STL入门

- 引用
- string
- 模板
- sort
- lower_bound
- unique
- vector
- set
- map
- 栈
- 队列
- priority_queue
- greater 比较器
- cin/cout 性能
- 随机数 srand
- rand 范围
- assert
- 函数重载
- 大整数类
- 前导零
- 运算符重载

### 第 6 章 数据结构基础

- 栈
- 队列
- deque
- 链表
- 数组模拟链表
- 双向链表
- 标记代替操作
- 内存池
- 内存泄漏
- 树与二叉树
- 完全二叉树编号
- 层次遍历
- 递归遍历
- 中序与后序构造二叉树
- 图
- DFS 连通块
- BFS 最短路
- 拓扑排序
- 欧拉回路
- 对拍
- 数据简化调试
- 离散化
- 数组模拟栈
- 数组模拟队列
- 头插法
- 二叉树层次遍历
- BFS 求最短路
- DFS 求连通块
- Euler 回路判定
- 并查集
- 路径压缩
- 优先队列
- 堆
- 哈希表
- map 作为哈希

### 第 7 章 暴力求解法

- 简单枚举
- 枚举排列
- 可重集排列
- 解答树
- 下一个排列
- 子集生成
- 增量构造法
- 位向量法
- 二进制子集
- 回溯法
- 八皇后
- 剪枝
- 路径寻找
- 八数码判重
- 康托展开
- 链式哈希表
- 迭代加深搜索
- IDA*
- 乐观估价函数
- 状态总数判据
- 排列判重
- 子集生成二进制法
- 八皇后问题
- 回溯剪枝
- 双向 BFS
- 隐式图 BFS
- 状态压缩搜索

### 第 8 章 高效算法设计

- 渐进时间复杂度
- 上界分析
- 算法分析结果
- 分治法
- 最大连续和
- 归并排序
- 逆序对计数
- 快速排序
- 二分查找
- 快速选择
- 二分答案
- 贪心法
- 部分背包
- 区间选点
- 区间覆盖
- Huffman
- 构造法
- 中途相遇法
- 问题分解
- 等价转换
- 扫描法
- 滑动窗口
- 单调队列
- 数形结合
- 规模与算法对应
- 手写 lower_bound
- STL 排序
- STL 去重
- STL 检索
- 前缀和
- 尺取法
- 离散化
- 贪心
- 折半枚举
- 分治
- 扫描线
- 单调栈
- Huffman 编码
- 数据规模与复杂度上限对应
- 指数级暴力适用规模
- 状态压缩 DP 适用规模
- 枚举全排列适用规模
- 状态总数可接受阈值
- O(n³) 可行规模
- O(n²) 可行规模
- O(n log n) 主战场规模
- O(n) 可行规模
- 快速选择与按值二分
- 大值域离散化
- 输入总量与边读边处理
- Eratosthenes 筛法复杂度
- 欧几里德算法复杂度
- 归并排序复杂度
- 快速排序复杂度
- 二分查找复杂度
- Huffman 编码复杂度
- 0-1 背包 DP 复杂度
- Kruskal 复杂度
- Dijkstra 复杂度
- Bellman-Ford 复杂度
- Floyd 复杂度
- 网络流增广路复杂度

### 第 9 章 动态规划初步

- 状态与状态转移方程
- 最优子结构
- 重叠子问题
- 记忆化搜索
- 递推
- 数字三角形
- DAG 上 DP
- 字典序最小方案
- 刷表法
- 滚动数组
- 0-1 背包
- 线性 DP
- 最长上升子序列
- 最长公共子序列
- 最优矩阵链乘
- 树形 DP
- 最大独立集
- 树的重心
- 树的最长路径
- 状态压缩 DP
- TSP
- 枚举所有子集
- 复杂度估算公式
- DAG 上的 DP
- 一维滚动数组
- LIS
- LCS
- 区间 DP
- 切木棍
- 树的最大独立集
- 最优配对
- TSP 状压 DP
- 集合 DP
- 多阶段决策
- 单调队列优化
- 输出格式严格匹配
- 禁止输出提示信息
- 程序输出后立即终止
- 禁用 conio.h 与 getch
- 行末回车与空格规范
- 多组数据空行与编号
- 超时的非效率原因
- 运行错的来源
- 实数输出加 EPS
- int 范围与位数
- long long 范围与格式符
- 中间结果溢出
- i*i 溢出
- 完全平方浮点比较
- 整数表达式每步取余
- Floyd INF 取值
- 费用流总费用用 long long
- 变量未初始化值不确定
- INF 初始化
- 多组数据变量重置
- 嵌套块同名变量屏蔽
- 循环体内变量重复声明
- 全局变量多组数据重置
- memset 只能赋 0 或 -1
- 记忆化搜索存回结果
- 没算过与无解区分
- 数组大小必须为常数
- 数组开大一点
- 大数组声明在 main 外
- 数组整体赋值与 memcpy
- 非法内存读写不报错
- gets 与 strcpy 溢出风险
- 字符串需存放 \0 的空间
- 数组作参数退化为指针
- 越界预判利用短路
- 递归深度与局部变量栈溢出
- *a++ 与 (*a)++
- 指针形参交换内容
- 未初始化指针写入崩溃
- 返回局部变量地址
- 不要滥用指针
- scanf 占位符与取地址
- scanf 返回值判断
- 输入结束符 Ctrl+Z 与 Ctrl+D
- 文件路径与扩展名
- 提交前删除重定向
- 条件编译与注释测试语句
- 换行符兼容
- 空串输入不能用 scanf
- 自增自减滥用
- 浮点循环变量累积误差
- 浮点递减循环结束值
- 整数除法负数行为
- 赋值是覆盖不是交换
- if 链需用 else if
- if 后多条语句加花括号
- -Wall 警告范围
- DFS 转有根树判父结点
- Kruskal 合并写代表元
- Dijkstra 不适用负权
- Bellman-Ford 迭代轮数与负圈判定
- 优先队列 Dijkstra 重复 push 去重
- 网络流反向弧成对与 i^1
- 有费用平行边不可合并
- 最小费用流初始无负权圈
- 混合图欧拉回路无向边定向
- 隐式图不预存整张图
- 网络流建模插头类型越界
- 矩阵解压先减 1 变换
- 循环流无最大流
- 递推顺序
- 刷表法适用条件
- 滚动数组与打印方案
- 字典序最小比较符号
- 找到转移后 break
- 状态定义不当导致转移困难
- 位运算优先级与括号
- 决策数影响复杂度
- 有环转移记忆化无限递归
- 括号序列两套转移
- 预累加未来费用适用边界
- 树形 DP 朴素枚举退化
- 数字三角形状态定义
- 状态转移方程
- 递推填表顺序
- DP 工作量估算
- 状态维度扩展

### 第 10 章 数学概念与方法

- 欧几里德算法
- 唯一分解定理
- 筛法
- 扩展欧几里德
- 同余
- 模算术
- 模逆元
- 快速幂
- 模乘
- 大整数取模
- 杨辉三角
- 二项式定理
- 组合数
- 约数个数
- 欧拉函数
- 编码与解码
- 离散概率
- 数学期望
- 全期望公式
- 连续概率
- 递推
- 数学归纳法
- Fibonacci
- 找规律陷阱
- gcd
- Eratosthenes 筛法
- 幂取模
- 组合数取模
- 杨辉三角递推
- 每步取模防溢出
- 期望线性性质
- 条件概率
- 几何概型
- 唯一分解
- 循环节
- 数位统计
- gcd 手写
- exgcd 手写
- 筛法手写
- 期望 DP
- 计数问题与概率期望建模差别

### 第 11 章 图论模型与算法

- 无根树转有根树
- 表达式树
- 最小生成树
- Kruskal
- 并查集
- 路径压缩
- Dijkstra
- 松弛操作
- 邻接表
- 优先队列优化
- Bellman-Ford
- 负圈判定
- Floyd
- 传递闭包
- 瓶颈路
- 网络流
- 残量网络
- 增广路
- 最小割最大流定理
- 最小费用最大流
- 拆点法
- 循环流
- 模板
- Kruskal 最小生成树
- 间接排序
- Dijkstra 邻接矩阵版
- Dijkstra 优先队列版
- 最大流 Edmonds-Karp
- 反向弧
- Dinic
- ISAP
- 最小割建模
- 二分图匹配
- 混合图欧拉回路
- 差分约束
- Kruskal 与并查集手写
- Dijkstra 两种实现
- Bellman-Ford 手写
- Floyd 手写
- EK 手写
- 最小费用最大流手写
- 三种最短路适用条件与复杂度
- 网络流建模拆点与最小割

### 第 12 章 高级专题

- DFA
- NFA
- ε-NFA
- ε-闭包
- DAWG
- 后缀自动机
- 点分治
- 树的重心选根
- 欧拉序列
- LCA 与 RMQ
- 树链剖分
- 轻重路径剖分
- Link-Cut 树
- 可持久化数据结构
- 可持久化栈
- 多边形布尔运算
- 扫描法
- 非完美算法
- 随机调整
- 模拟退火
- 难题分类
- AC 自动机
- Trie
- KMP
- 后缀数组
- LCP
- 字符串 Hash
- Treap
- 伸展树
- 名次树
- 几何基础

### 附录A 开发环境与方法

- 命令行
- 文件系统
- 重定向与管道
- 批处理脚本
- Bash 脚本
- gcc 编译选项
- gdb 调试
- IDE

### 第 5 章 C++ 与 STL 入门

- STL 容器
- 集合编码
- 队列嵌套队列
- 列对齐
- 列对哈希
- 排序与名次
- 字符串解析模拟
- 扫描线去重
- set 查词
- 优先队列与队列协同
- map 差集
- 大整数类 BigInteger
- vector 存各位数字
- 运算符重载

### 第 12 章 进阶算法与训练指南

- 三步走学习路径
- 难题题解看两遍并独立推导

### 训练计划

- 语言与格式周
- 数组与字符串周
- 函数递归与调试周
- C++ 与 STL 周
- 数据结构基础周
- 暴力与回溯周
- 算法分析与排序分治周
- 贪心与优化策略周
- 动态规划模型周
- 动态规划进阶模型周
- 数学与数论周
- 图论与网络流周
- 整轮验收标准
- 卡住时自救顺序

## 鸟哥的 Linux 私房菜·基础学习篇

### 第 0 章 计算机概论

- 计算机硬件五大单元
- RISC 与 CISC
- 容量单位进位
- 硬盘组成
- 数据表示与进制互换
- 编码表
- 编译程序
- 操作系统职责

### 第 1 章 Linux 是什么

- Linux 内核与完整系统
- UNIX 历史
- GNU 项目
- Linux 0.02
- 虚拟团队开发
- 内核版本号规则
- distribution 组成
- GPL 授权

### 第 2 章 Linux 如何学习

- 企业环境与个人环境角色
- 学习心态
- 从零学基础
- 选一本工具书读完
- 实践再实践
- 发生问题的处理顺序
- Solution 导向学习

### 第 3 章 主机规划与磁盘分区

- 硬件设备文件名
- 磁盘连接方式
- 磁盘组成
- 分区表与 MBR
- 主分区与扩展分区
- MBR 与 boot loader
- 安装时的分区选择
- distribution 选择
- 主机服务规划
- 练习机安装建议
- 大硬盘无法开机

### 第 4 章 安装 CentOS 5.x 与多重引导小技巧

- 安装前分区规划
- BIOS 启动顺序与 SATA 模式
- 语系选择
- 分区界面挂载点设置
- GRUB 安装位置
- 网络与时区设置
- root 密码设置
- 软件选择
- 首次设置建日常账号
- 多重引导三情形
- 大硬盘无法开机对策

### 第 5 章 首次登录与在线求助 man page

- 登录提示信息
- 提示符 $ 与 #
- 命令语法格式
- LANG 临时改语系
- date/cal/bc
- Tab 补全
- Ctrl-c 与 Ctrl-d
- command not found 成因
- man 手册章节编号
- man -f 与 man -k
- info 在线手册
- sync 与 shutdown
- init 切换 run level
- 开机排错

### 第 6 章 Linux 的文件权限与目录配置

- 文件所有者与用户组
- ls -l 十列
- chmod 数字法与符号法
- chown 与 chgrp
- 目录权限 rwx 含义
- 文件类型
- FHS
- 目录树
- 绝对路径与相对路径

### 第 7 章 Linux 文件与目录管理

- cd/pwd/mkdir/rmdir
- PATH 与命令查找
- ls 常用参数
- cp 参数
- rm 与 alias
- 文件内容查看命令
- cat -A 抓空白差异
- tail -f
- touch 与三个时间
- umask
- chattr 与 lsattr
- SUID/SGID/SBIT
- which/whereis/locate/find
- find 特殊权限筛选
- 权限与命令的对应

### 第 8 章 Linux 磁盘与文件系统管理

- inode 区与 block 区
- inode 记录内容
- 目录树访问路径
- Ext3 journal
- df 与 du
- 硬链接与符号链接
- fdisk 分区
- mkfs 与 mke2fs
- fsck 与 badblocks
- mount 与 umount
- dumpe2fs 与 tune2fs
- fstab 开机挂载
- loop 挂载
- swap 构建
- parted 大分区

### 第 9 章 文件与文件系统的压缩与打包

- 压缩原理
- compress/gzip/bzip2
- zcat 与 bzcat
- tar 打包与解包
- tar 排除路径
- tar 解出单个文件
- 备份脚本组织
- dump 完整与增量备份
- restore 还原
- mkisofs 与 cdrecord
- dd 整盘复制
- cpio

### 第 10 章 vim 程序编辑器

- vim 必要性
- vim 三模式
- 按键操作表
- swp 文件恢复
- 块选择
- 多文件与多窗口
- vimrc 与 viminfo
- 中文乱码与编码变量
- DOS 断行字符
- iconv 编码转换

### 第 11 章 认识与学习 bash

- shell 与内核
- /etc/shells
- type 判断命令类型
- 变量设置与删除
- 环境变量
- locale
- export 与子进程
- read 与 declare
- ulimit
- 变量内容替换
- alias 与 history
- 命令查找顺序
- issue 与 motd
- 环境配置文件读取顺序
- stty 与 set
- 通配符与特殊符号
- 重定向
- 分号与 && 与 ||
- 管线
- cut/grep/sort/wc/uniq/tee/tr/col/join/paste/expand/split/xargs
- 管线中的 -

### 第 12 章 正则表达式与文件格式化处理

- 正则与通配符区别
- 语系对正则的影响
- grep 参数
- 基础正则字符
- sed 用法
- 扩展正则
- printf
- awk 字段处理
- diff 与 cmp
- patch 应用与还原
- pr 排版

### 第 13 章 学习 shell script

- script 的价值
- 第一支 script
- 三种执行方式
- script 良好习惯
- test 判断
- 中括号判断语法
- 默认变量 $0/$1/$#/$@
- if 与 case
- function
- while/until/for
- sh -n 与 sh -x

### 第 14 章 Linux 账号管理与 ACL 权限设置

- UID 与 GID
- 系统账号与一般账号 UID 区间
- useradd 行为决定文件
- passwd 参数
- chage
- usermod
- userdel
- groupadd/groupmod/gpasswd
- ACL 概念
- ACL 挂载选项
- setfacl 与 getfacl
- su 与 sudo
- sudoers 与 visudo
- nologin shell
- PAM 配置
- w/who/last/lastlog
- write/wall/mail
- 手工建号
- 批量建号

### 第 15 章 磁盘配额（Quota）与高级文件系统管理

- Quota 限制类型
- Quota 实践五步
- Quota 替代方案
- RAID 0/1/5
- mdadm 软 RAID
- mdadm.conf 与关闭顺序
- LVM 的 PV/VG/PE/LV
- LVM 在线放大
- LVM 缩小顺序
- LVM 快照
- LVM 命令分组

### 第 16 章 例行性工作（crontab）

- at 与 atd
- at.allow 与 at.deny
- at -l 与 atrm
- 用户 crontab -e
- /etc/crontab 多一栏
- cron.daily 与 run-parts
- cron 注意事项
- anacron
- anacrontab
- 0anacron 挂钩

### 第 17 章 程序管理与 SELinux 初探

- process 与 program
- 多用户多任务
- 后台与作业管理
- 作业管理作用范围
- 脱机管理
- ps 与 top 与 pstree
- kill 与 killall
- nice 与 renice
- free/uname/uptime
- SUID/SGID 执行状态
- /proc 虚拟文件系统
- fuser 与 lsof
- SELinux 强制访问控制
- SELinux 三模式
- SELinux 类型标签处理

### 第 18 章 认识系统服务（daemons）

- daemon 分类
- /etc/services 端口对应
- 启动脚本与 /etc/init.d
- xinetd.conf 与 xinetd.d
- rsync xinetd 范例
- TCP Wrappers 规则
- TCP Wrappers 额外功能
- chkconfig 与 netstat 查服务
- chkconfig 与 ntsysv 设启动
- CentOS 5 默认服务

### 第 19 章 认识与分析日志文件

- 日志用途
- syslogd
- 日志格式
- syslog.conf 语法
- 日志安全性
- 日志服务器
- logrotate 配置
- logrotate -f 测试
- 自定义轮替
- logwatch
- 自写日志分析工具

### 第 20 章 启动流程、模块管理与 Loader

- 启动八步
- BIOS 与 POST 与 INT 13
- boot loader 三功能
- Windows loader 不转交
- 内核文件与模块目录
- initrd 存在原因
- initrd 结构与 init
- /sbin/init 与 PID 1
- /etc/inittab
- run level 0/4/6 不可默认
- rc.sysinit
- rcN.d 的 S/K 命名
- rc.local
- 模块管理命令
- modprobe.conf
- GRUB 两 stage 与 menu.lst
- 忘记 root 密码
- 启动失败处理
- chroot 救援

### 第 21 章 系统设置工具与硬件检测

- setup 统一入口
- CUPS 四层结构
- CUPS 联机模式与 Web 管理
- 本地与网络打印机
- 手动配置打印机
- 硬件信息收集
- USB 驱动与 udev
- lm_sensors

### 第 22 章 软件安装：源码与 Tarball

- 开源与源码
- 动态库与静态库
- configure 与 make
- Tarball
- gcc 编译与链接
- makefile 语法与变量
- Tarball 安装三步骤
- ntp 安装示范
- patch 应用与还原
- ldconfig 与 ld.so.conf
- ldd 查依赖
- MD5 校验

### 第 23 章 软件安装：RPM、SRPM 与 YUM 功能

- RPM 与 DPKG
- RPM 与 SRPM
- 平台标记
- RPM 优点
- YUM 解决依赖
- RPM 默认安装路径
- rpm 安装与查询参数
- GPG 校验
- rpm --rebuilddb
- SRPM 重建
- spec 文件结构
- 打包范例
- yum 常用子命令
- yum.repos.d 配置
- 软件组
- 全系统自动升级
- RPM 与 Tarball 抉择

### 第 24 章 X Window 设置介绍

- X Client/Server 架构
- Window Manager 与 Display Manager
- X 启动流程
- 纯文本运行
- xorg.conf 段落
- XFS 与字体
- 设置重建与微调
- 显卡驱动安装

### 第 25 章 Linux 备份策略

- 备份要点
- 该备份的数据
- 备份设备选择
- 增量备份
- 差异备份
- 关键数据高频备份
- 每周系统备份 script
- 每日数据备份 script
- 远程备份 script
- 灾难恢复顺序

### 第 26 章 Linux 内核编译与管理

- 内核角色
- 更新内核目的
- 内核版本号规则
- 源码取得与放置
- make mrproper
- make menuconfig 等
- Kconfig 逐项选择
- make 与 modules_install
- 装新内核与 GRUB 菜单
- 单模块编译
- 内核模块管理命令

### 第 6 章 命令速查表

- 文件与目录命令
- ls 参数
- cd 与 pwd
- mkdir 与 rmdir
- cp 参数
- rm 参数
- mv 参数
- basename 与 dirname
- touch 参数
- file 命令
- which 命令
- type 命令
- whereis 命令
- locate 命令
- find 命令
- ln 命令
- rename 命令
- 文件内容查看命令
- cat 参数
- tac 命令
- nl 命令
- more 与 less
- head 与 tail
- od 命令
- wc 命令
- 权限与所有者命令
- chmod 参数
- chown 与 chgrp
- umask 命令
- chattr 与 lsattr
- getfacl 与 setfacl
- 进程与作业命令
- ps 命令
- top 命令
- pstree 命令
- kill 与 killall
- jobs 与 fg 与 bg
- nice 与 renice
- free 命令
- uname 命令
- uptime 命令
- fuser 命令
- lsof 命令
- nohup 命令
- 磁盘与文件系统命令
- df 命令
- du 命令
- fdisk 命令
- parted 命令
- mkfs 命令
- mke2fs 命令
- fsck 命令
- badblocks 命令
- dumpe2fs 命令
- tune2fs 命令
- hdparm 命令
- mount 命令
- umount 命令
- swapon 与 mkswap
- 压缩与打包命令
- gzip 与 zcat
- bzip2 与 bzcat
- tar 命令
- dump 命令
- restore 命令
- mkisofs 命令
- cdrecord 命令
- dd 命令
- cpio 命令
- vim 命令
- vim 模式切换
- vim 存盘与退出
- vim 编辑操作
- vim 查找
- vim 块选择
- vim 多窗口
- dos2unix 与 unix2dos
- iconv 命令
- bash 与变量命令
- echo 命令
- unset 命令
- export 命令
- read 命令
- declare 命令
- ulimit 命令
- alias 与 unalias
- history 命令
- stty 命令
- set 命令
- locale 命令
- date 命令
- cal 命令
- bc 命令
- 正则与文本处理命令
- grep 命令
- sed 命令
- awk 命令
- printf 命令
- cut 命令
- sort 命令
- uniq 命令
- tee 命令
- tr 命令
- col 命令
- join 命令
- paste 命令
- expand 命令
- split 命令
- xargs 命令
- diff 命令
- cmp 命令
- patch 命令
- pr 命令
- shell script 语法
- shebang 声明
- test 条件测试
- 中括号条件简写
- 默认变量
- if 分支
- case 多分支
- function 函数
- while 与 until 循环
- for 循环
- sh -n 语法检查
- sh -x 追踪执行
- source 命令
- 账号管理命令
- useradd 命令
- passwd 命令
- chage 命令
- usermod 命令
- userdel 命令
- chsh 命令
- groupadd 命令
- groupmod 命令
- gpasswd 命令
- groups 命令
- newgrp 命令
- su 命令
- sudo 命令
- visudo 命令
- w 与 who
- last 与 lastlog
- write 与 wall 与 mesg
- 磁盘配额命令
- quotacheck 命令
- quotaon 与 quotaoff
- edquota 命令
- quota 与 repquota
- warnquota 命令
- RAID 命令
- mdadm 命令
- LVM 命令
- pvcreate 与 pvscan 与 pvdisplay
- vgcreate 与 vgscan 与 vgdisplay
- lvcreate 与 lvscan 与 lvdisplay
- lvextend 与 lvreduce
- resize2fs 命令
- 计划任务命令
- at 命令
- atq 命令
- atrm 命令
- crontab 命令
- anacron 命令
- 服务与日志命令
- chkconfig 命令
- ntsysv 命令
- service 命令
- init.d 启动脚本
- netstat 命令
- syslogd 与 klogd
- logrotate 命令
- logwatch 命令
- dmesg 命令
- 开机流程与内核模块命令
- sync 命令
- shutdown 命令
- reboot 与 halt 与 poweroff
- init 命令
- runlevel 命令
- lsmod 命令
- modinfo 命令
- modprobe 命令
- insmod 命令
- rmmod 命令
- depmod 命令
- chroot 命令
- grub 命令
- mkinitrd 命令
- 软件安装命令
- rpm 安装
- rpm 升级
- rpm 查询
- rpm 验证
- rpm 导入密钥
- rpm 卸载
- rpm 重建数据库
- rpmbuild 命令
- yum 命令
- gcc 命令
- make 命令
- configure 脚本
- ldconfig 命令
- ldd 命令
- md5sum 命令

### 第 7 章 配置文件清单

- 账号相关配置文件
- passwd 文件
- shadow 文件
- group 文件
- gshadow 文件
- useradd 默认值文件
- login.defs 文件
- skel 目录
- shells 文件
- PAM 配置文件
- limits.conf 文件
- sudoers 文件
- 挂载相关配置文件
- fstab 文件
- mtab 文件
- filesystems 文件
- mdadm.conf 文件
- dumpdates 文件
- 登录信息配置文件
- issue 文件
- issue.net 文件
- motd 文件
- shell 环境配置文件
- profile 文件
- bashrc 文件
- profile.d 目录
- bash_profile 文件
- bash_history 文件
- bash_logout 文件
- inputrc 文件
- man.config 文件
- updatedb.conf 文件
- termcap 文件
- DIR_COLORS 文件
- sysconfig 配置文件
- i18n 文件
- clock 文件
- network 文件
- keyboard 文件
- iptables 文件
- authconfig 文件
- resolv.conf 文件
- hosts 文件
- services 文件
- inittab 文件
- rc.sysinit 脚本
- rcN.d 目录
- rc.local 脚本
- init.d 目录
- modprobe.conf 文件
- modules 目录
- GRUB 配置文件
- menu.lst 文件
- device.map 文件
- xinetd 配置文件
- xinetd.conf 文件
- xinetd.d 目录
- hosts.allow 文件
- hosts.deny 文件
- syslog.conf 文件
- sysconfig/syslog 文件
- logrotate.conf 文件
- logrotate.d 目录
- crontab 文件
- cron 分频目录
- cron.allow 与 cron.deny
- at.allow 与 at.deny
- anacrontab 文件
- SELinux 配置文件
- selinux/config 文件
- sestatus.conf 文件
- ld.so.conf 文件
- ld.so.cache 文件
- yum.repos.d 目录
- rpm-gpg 密钥目录
- xorg.conf 文件
- X11 字体配置
- cupsd.conf 文件
- printers.conf 文件
- udev 规则目录
- lm_sensors 文件
- warnquota.conf 文件
- rpm 数据库目录
- vimrc 文件
- viminfo 文件

### 第 8 章 故障排查剧本

- command not found 排查
- 输出乱码排查
- 前台程序中断
- 权限不足无法进入目录
- immutable 属性导致无法删除
- 命令存在但 which 找不到
- inode 用尽导致无法写入
- 设备忙无法卸载
- fstab 错误导致无法开机
- 忘记 root 密码
- 文件系统错误无法启动
- inittab 改错无法开机
- BIOS 磁盘对应错误
- 系统时间时区错误
- 端口被占用
- xinetd 服务不生效
- 日志轮替现象
- RPM 数据库损坏
- YUM 安装失败
- 动态库找不到
- 打补丁失败
- 网络不通排查

### 第 9 章 名词表

- Linux 定义
- distribution 定义
- GNU 定义
- GPL 定义
- MBR 定义
- boot loader 定义
- GRUB 定义
- boot sector 定义
- 分区表定义
- 主分区与扩展分区与逻辑分区
- inode 定义
- block 定义
- super block 定义
- journal 定义
- ext2 与 ext3
- VFS 定义
- 挂载与挂载点
- loop 设备
- swap 定义
- LVM 定义
- PV 与 VG 与 PE 与 LV
- RAID 0 与 1 与 5
- Quota 定义
- FHS 定义
- 绝对路径与相对路径
- SUID 与 SGID 与 SBIT
- umask 定义
- ACL 定义
- PAM 定义
- nologin 定义
- SELinux 定义
- daemon 定义
- stand alone 与 super daemon
- xinetd 定义
- TCP Wrappers 定义
- syslogd 定义
- logrotate 定义
- cron 与 at 与 anacron
- run level 定义
- init 定义
- rc.sysinit 定义
- initrd 定义
- rc.local 定义
- process 与 program
- job control 定义
- nice 与 renice 定义
- proc 文件系统
- RPM 与 SRPM
- YUM 定义
- DPKG 定义
- Tarball 定义
- configure 与 make
- makefile 定义
- 动态库与静态库
- ldconfig 定义
- ldd 定义
- patch 与 diff
- 正则表达式定义
- 通配符定义
- 管线定义
- 重定向定义
- 变量与环境变量
- locale 定义
- var 目录
- MBR 与 GRUB stage
- menu.lst 定义
- 单用户模式定义
- chroot 定义
- SELinux 三模式
- 日志设施与等级
- 增量与差异备份
- 软 RAID 定义
- 磁盘配额软硬限制

### 第 10 章 局限与坑

- 时代坐标
- init 到 systemd
- syslogd 到 rsyslog/journald
- ext3 到 ext4/xfs
- ifconfig 到 ip
- GRUB legacy 到 GRUB2
- ntp 到 chrony
- modprobe.conf 到 modprobe.d
- chkconfig 到 systemctl
- setup 工具消失
- X Window 不再默认安装
- 大硬盘与旧 BIOS
- fstab 写错无法开机
- inittab 默认 run level 陷阱
- umount 前检查占用
- rpm -e 依赖问题
- chmod -R 777 与 ACL
- kill -9 与 SIGTERM
- 书中未覆盖内容清单
- 命令表与配置表的使用建议

### 第 11 章 费曼自检：从按下电源到看见登录提示符

- BIOS 自检与启动设备选择
- MBR 主引导记录
- GRUB 引导装载程序
- 多系统安装顺序
- 内核加载与硬件检测
- initrd 初始内存虚拟文件系统
- init 1 号进程
- inittab 与 run level
- rc.sysinit 脚本
- 服务启动
- rc.local
- tty 与 login
- shell 提示符含义
- 启动链故障定位

### 第 12 章 实操路线：8 周动手计划

- 硬件前提与虚拟化
- 系统选择 Rocky/Alma Linux
- 每日节奏与记录方法
- 第 1 周 分区与安装
- 分区方案规划
- 系统安装
- 首次登录与提示符
- 命令语法与入门命令
- 救命热键与 man 求助
- 关机与开机排错
- 第 2 周 文件权限与目录树
- ls -l 十列含义
- chmod 数字法与符号法
- 目录 rwx 含义
- FHS 目录树
- 文件与目录操作
- PATH 与执行
- 查看文件内容
- umask 与隐藏属性
- 第 3 周 磁盘与文件系统
- inode 与 block
- 硬链接与软链接
- 分区格式化挂载
- fstab 与开机挂载
- swap
- 压缩与打包
- 备份工具 dump/restore/dd
- 第 4 周 编辑器与 shell 基础
- vim 三模式
- vim 进阶与 .swp
- 变量与环境变量
- 别名历史与配置文件
- 重定向与管线
- 正则表达式基础
- 里程碑装第二台虚拟机
- 第 5 周 文本处理与脚本
- sed
- awk
- 第一支 script
- 判断式 if/case
- 循环 while/for/until
- 函数与调试 sh -x
- 里程碑备份脚本
- 第 6 周 账号配额计划任务
- 账号三件套
- 期限与用户组
- ACL
- su 与 sudo
- nologin 账号与 PAM
- 计划任务 at/cron
- 磁盘配额
- 第 7 周 进程服务日志开机
- 进程与作业
- 进程管理与优先级
- /proc 与文件占用
- 服务与端口
- 日志与轮替
- 从 BIOS 到 login
- 救援演练
- 第 8 周 软件内核备份
- RPM 基础
- YUM
- Tarball 编译
- 库管理
- 内核模块
- 内核编译
- 备份策略与恢复演练
- 收尾成果清单
