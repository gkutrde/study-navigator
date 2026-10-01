python
## 变量
```r
greet = "您好，吃了吗？"
greet_chinese = greet
greet_enlish = "Yo what's up,"
greet = greet_enlish
print(greet + "张三")
print(greet + "李四")
print(greet + "王五")
```
## 数学运算
```r
import math
a = -1
b = -2
c = 3
print((-b + math.sqrt(b**2 - 4*a*c))/(2*a))
print((-b - math.sqrt(b**2 - 4*a*c))/(2*a))
```
## 位运算符
| 运算符 | 描述 |
| --- | --- |
| & | 参与运算的两个值，如果两个相应位的值都为1，则该位的结果为1，否则为0 |
| \| | 只要对应的二进制两个二进位有一个为1，结果就为1 |
| ^ | 当两对应的二进位相异时，结果为1 |
| ~ | 对数据的每个二进位取反 |
| << | 运算数的各二进位全部左移若干位，由"<<"右边的数指定移动的位数，高位丢弃，低位补0 |
| >> | 与上相反 |
    运算符
    描述
    &
    参与运算的两个值，如果两个相应位的值都为1，则该位的结果为1，否则为0
    |
    只要对应的二进制两个二进位有一个为1，结果就为1
    ^
    当两对应的二进位相异时，结果为1
    ~
    对数据的每个二进位取反
    <<
    运算数的各二进位全部左移若干位，由"<<"右边的数指定移动的位数，高位丢弃，低位补0
    >>
    与上相反
## 身份运算符
1. is类似于id()==id()
2. is not类似于id()!=id()
- is和==的区别：*is 用于判断两个变量引用对象是否为同一个， == 用于判断引用变量的值是否相等*
## 数据类型
### 字符串 str
```r
len(' 6 ')#空格也算一个字符串长度，\n也算一个字符串长度
print("Hello"[3])#程序的世界从0开始计数，输出l
```
字符串可以拼接
```r
a = "Hello World"
print("已更新字符串：" + a[:] + 'Runoob')
```
#### 转义字符
| \\ | 输出反斜杠本身 |
| --- | --- |
| \' | 在单引号字符串中输出单引号 |
| \" | 在双引号字符串中输出双引号 |
| \n | 换行 |
| \t | 水平制表符 |
| \r | 回车，将 **\r** 后面的内容移到字符串开头，并逐一替换开头部分的字符，直至将 **\r** 后面的内容完全替换完成 |
| \xhh | 十六进制转义 |
    \\
    输出反斜杠本身
    \'
    在单引号字符串中输出单引号
    \"
    在双引号字符串中输出双引号
    \n
    换行
    \t
    水平制表符
    \r
    回车，将 **\r** 后面的内容移到字符串开头，并逐一替换开头部分的字符，直至将 **\r** 后面的内容完全替换完成
    \xhh
    十六进制转义
#### 字符串格式化（%不推荐，现代替代方案）
f-string
```r
print(f"Hello, {name}. You are {age} years old.")
```
### 整数 int
### 浮点数 float
### 复数
a + bj或complex(a,b)
### 布尔类型 bool
### 空值类型 NoneType
```r
#对字符串求长度
s = "Hello world!"
print(len(s))
#通过索引获取单个字符
print(s[0])
print(s[11])#print(s[len(s)-1])
#布尔类型
b1 = True
b2 = False
#空值类型
n = None
#type函数
print(type(s))
print(type(b1))
print(type(n))
print(type(1.5))
```
## 用户问答交互
```r
user_weight = float(input("请输入您的体重（单位：kg）"))
user_height = float(input("请输入您的身高（单位：m）"))
user_BMI = user_weight / (user_height) ** 2
print("您的BMI值为：" + str(user_BMI))
```
## 条件控制
```r
mood_index = int(input("对象今天的心情指数是："))
if mood_index >= 60:
    print("恭喜，今晚应该可以打游戏，去吧，皮卡丘！")
else:
    print("为了自个儿小命，还是别打了。")
```
### if嵌套
```r

user_weight = float(input("请输入您的体重（单位：kg）"))
user_height = float(input("请输入您的身高（单位：m）"))
user_gendor = str(input("请输入您的性别："))
user_BMI = user_weight / (user_height) ** 2
print("您的BMI值为：" + str(user_BMI))

if user_BMI <= 18.5:
    if user_gendor == "男":
        print("尊敬的先生，此BMI值属于偏瘦范围。")
    else:
        print("尊敬的女士，此BMI值属于偏瘦范围。")
elif 18.5 < user_BMI <= 25:
    if user_gendor == "男":
        print("尊敬的先生，此BMI值为正常范围。")
    else:
        print("尊敬的女士，此BMI值为正常范围。")
elif 25 <user_BMI <= 30:
    if user_gendor == "男":
        print("尊敬的先生，此BMI值属于偏胖范围。")
    else:
        print("尊敬的女士，此BMI值属于偏胖范围。")
else:
    if user_gendor == "男":
        print("尊敬的先生，此BMI值属于肥胖范围。")
    else:
        print("尊敬的女士，此BMI值属于肥胖范围。")
```
### match...case 的条件判断（python3.10+）
```r
value = 25

match value:
    case int(x) if x > 0:      # 匹配整数，且必须大于 0
        print(f"正数: {x}")
    case int(x) if x < 0:
        print(f"负数: {x}")
    case int(x):               # 匹配整数，但没有守卫（兜底 0）
        print("零")
    case _:
        print("不是整数")
```
### 多条件判断
```r
user_weight = float(input("请输入您的体重（单位：kg）"))
user_height = float(input("请输入您的身高（单位：m）"))
user_BMI = user_weight / (user_height) ** 2
print("您的BMI值为：" + str(user_BMI))

if user_BMI <= 18.5:
    print("此BMI值属于偏瘦范围。")
elif 18.5 < user_BMI <= 25:
    print("此BMI值为正常范围。")
elif 25 <user_BMI <= 30:
    print("此BMI值属于偏胖范围。")
else:
    print("此BMI值属于肥胖范围。")
```
## 逻辑运算
### not>and>or,可以通过括号改变顺序
### 假值：
False/None/0/0.0/""/[]/()/{}/set()
### 规则
3. and的规则
- 如果左为假，直接返回左边的值
- 如果左为真，返回右边的值
```r
0 and 5 #0
1 and 5 #5
"" and "abc" #""
"a" and "b" #"b"
```
4. or的规则
- 如果左为真，直接返回左边的值
- 如果左为假，返回右边的值
```r
1 or 5      # 1
0 or 5      # 5
"a" or "b"  # "a"
"" or "b"   # "b"
```
### 短路运算
```r
def f():
    print("执行好了")
    return True
False and f()#不会执行
True or f()#不会执行
```
## 列表
```go
shopping_list = []
shopping_list.append("键盘")
shopping_list.append("键帽")
shopping_list.remove("键盘")
shopping_list.append("音响")
shopping_list.append("电竞椅")
shopping_list[1] = "硬盘"
print(shopping_list)
print(len(shopping_list))
print(shopping_list[0])
```
```r
price = [799,1024,200,800]
max_price = max(price)
min_price = min(price)
sorted_price = sorted(price)
print(max_price)
print(min_price)
print(sorted_price)
```
### 嵌套列表
```r
a = ["a","b","c"]
n = [1,2,3]
x = [a,n]
print(x[0])#输出["a","b","c"]
print(x[0][1])#输出b
```
### 列表比较
```r
import operator
a = [1,2]
b = [2,3]
c = [2,3]
print(operator.eq(a,b))#False
print(operator.eq(c,b))#True
```
## 元组
```r
tup1 = (1,2,3,4)
tup2 = (1,)#当元组只有一个元素时，要添加逗号
```
```r
list = [1,2,3]
tup1 = tuple(list)
print(tup1)#输出(1,2,3)
```
## 字典
```r
dic = {"你好":"打招呼",
        "Hello":"英文打招呼1"}
dic["hi"] = "英文打招呼2"#添加进入字典
query = input("请输入你要查询的内容")
if query in dic:#判断是否在字典
    print("您查询的" + query + "含义为：")
    print(dic[query])#打印键对应的值
else:
    print("该词暂未收录")
    print("本站已经收录：" + str(len(dic)) + "条。")
```
**只能改值或键值对或添加新的键值对**
### 键的特性
#### 不允许一个键出现两次。创建时如果一个键被赋值两次，后一个值会被记住
#### 键必须不可变，所以可以用数字，字符串和元组充当，而列表就不行
## 集合
集合可以用{}或set（）创建
```r
set1 = {1, 2, 3, 4}            # 直接使用大括号创建集合
set2 = set([4, 5, 6, 7])      # 使用 set() 函数，括号中要为可迭代数据：字符串、列表元组
```
**创建一个空集合要用set（）**
```r
a - b#a有b无
a | b#a并b
a & b#a交b
a ^ b#a交b的补集
```
### 集合的基本操作
5. 添加元素
s.add()只能添加单个元素（整数、字符串、元组等可哈希对象）
```r
thisset = set(("Google", "Runoob", "Taobao"))
thisset.add("Facebook")
**print**(thisset)#{'Taobao', 'Facebook', 'Google', 'Runoob'}
```
s.update()批量添加多个元素，可以接受任意数量的可迭代对象（如列表、元组、字符串、字典、另一个集合等），多个参数用逗号分隔
```r
s = {1, 2, 3}
s.update([4, 5])          # 添加列表中的元素
print(s)                  # {1, 2, 3, 4, 5}

s.update((6, 7), {8, 9})  # 同时添加元组和集合中的元素
print(s)                  # {1, 2, 3, 4, 5, 6, 7, 8, 9}

s.update("abc")           # 字符串被视为可迭代对象，添加字符 'a','b','c'
print(s)                  # {1, 2, 3, 4, 5, 6, 7, 8, 9, 'a', 'b', 'c'}
```
6. 移除元素
```r
s.remove(x)#将元素 x 从集合 s 中移除，如果元素不存在，则会发生错误
```
```r
s.discard( x )#如果元素不存在，不会发生错误
```
```r
s.pop()#随机删除一个元素
```
7. 计算元素个数
```r
len(s)
```
8. 清空集合
```r
s.clear()
```
9. 判断元素是否在集合里
```r
x in s
```
## 循环语句
### for循环
```r
temperature_dict = {"111": 36.5, "112": 38.2, "113": 40.0}
# temperature_dict.keys()    # 所有键
# temperature_dict.values()  # 所有值
# temperature_dict.items()   # 所有键值对
for staff_id, temperature in temperature_dict.items():
    '''等价于
    for temperature_tuple in temperature_dict.items():
        staff_id = temperature_tuple[0]
        temperature = temperature_tuple[1]
        if temperature >= 37.3:
            print(staff_id)
    '''
    if temperature >= 37.3:
        print(staff_id)
```
```r
for i in range(4,7):#起始值计入，结束值不计入
    print(i)
```
```r
total = 0
for i in range(1,101,1):
    total = total + i#第一次total为1，第二次为1+2，第三次为1+2+3......
print(total)#print没有缩进，不归for管
```
### while循环
```r
user_input = input("请输入你的数字：")
total = 0
count = 0
while user_input != "q":
    num = float(user_input)
    total = total + num
    count = count + 1
    user_input = input("请输入你的数字：")
if count == 0:
    print("平均数为：0")
else:
    result = total / count
    print("平均数为：" + str(result))
```
```r
count = 0
while count < 5:
   print (count, " 小于 5")
   count = count + 1
else:
   print (count, " 大于或等于 5")
```
### break破坏循环
```r
n = 5
while n > 0:
    n -= 1
    if n == 2:
        break
    print(n)
print('循环结束。')
```
### continue跳过循环剩余语句，然后执行下一轮循环
```r
n = 5
while n > 0:
    n -= 1
    if n == 2:
        continue
    print(n)
print('循环结束。')
```
### else语句
```r
for n in range(2, 10):
    for x in range(2, n):
        if n % x == 0:
            print(n, '等于', x, '*', n//x)
            break
    else:
        # for 循环没有被 break 中断（正常跑完），才执行 else
        print(n, ' 是质数')
```
## 推导式
### 列表推导式
```r
[表达式 for 变量 in 列表]
[表达式 for 变量 in 列表 if 条件]
```
```r
multiples = [i for i in range(30) if i % 3 == 0]
print(multiples)#[0, 3, 6, 9, 12, 15, 18, 21, 24, 27]
```
### 字典推导式
```r
{key_expr:value_expr for value in collection}
{key_expr:value_expr for value in collection if conditional}
```
```r
# 只保留偶数
even_squares = {x: x**2 for x in range(10) if x % 2 == 0}
print(even_squares)
# {0: 0, 2: 4, 4: 16, 6: 36, 8: 64}
```
### 集合推导式
```r
{expression for item in Sequence}
或
{expression for item in Sequence if conditional}
```
```r
a = {x for x in 'abracadabra' if x not in 'abc'}
print(a)#{'d', 'r'}
```
### 元组推导式
```r
tuple(expression for item in Sequence)
或
tuple(expression for item in Sequence if conditional)
```
```r
t = tuple(x for x in range(1, 10))
print(t)  # (1, 2, 3, 4, 5, 6, 7, 8, 9)
```
## 迭代器与生成器
### 迭代器
迭代器有两个基本的方法：**iter()** 和 **next()**；字符串，列表或元组对象都可用于创建迭代器
```r
list=[1,2,3,4]
it = iter(list)    # 创建迭代器对象
print (next(it))   # 输出迭代器的下一个元素    1
print (next(it))#2
```
```r
list=[1,2,3,4]
it = iter(list)    # 创建迭代器对象
for x in it:
    print (x, end=" ")
```
#### 创建一个迭代器
```r
class MyNumbers:
  def __iter__(self):
    self.a = 1
    return self
 
  def __next__(self):
    x = self.a
    self.a += 1
    return x
 
myclass = MyNumbers()
myiter = iter(myclass)
 
print(next(myiter))
print(next(myiter))
print(next(myiter))
print(next(myiter))
print(next(myiter))
'''
1
2
3
4
5
'''
```
#### StopIteration
StopIteration 异常用于标识迭代的完成，防止出现无限循环的情况，在 **next**() 方法中我们可以设置在完成指定循环次数后触发 StopIteration 异常来结束迭代
```r
class MyNumbers:
  def __iter__(self):
    self.a = 1
    return self
 
  def __next__(self):
    if self.a <= 20:
      x = self.a
      self.a += 1
      return x
    else:
      raise StopIteration
 
myclass = MyNumbers()
myiter = iter(myclass)
 
for x in myiter:
  print(x)
```
### 生成器
跟普通函数不同的是，生成器是一个返回迭代器的函数，只能用于迭代操作，更简单点理解生成器就是一个迭代器
当在生成器函数中使用 **yield** 语句时，函数的执行将会暂停，并将 **yield** 后面的表达式作为当前迭代的值返回。然后，每次调用生成器的 **next()** 方法或使用 **for** 循环进行迭代时，函数会从上次暂停的地方继续执行，直到再次遇到 **yield** 语句
```r
def countdown(n):
    while n > 0:
        yield n
        n -= 1
 
# 创建生成器对象
generator = countdown(5)
 
# 通过迭代生成器获取值
print(next(generator))  # 输出: 5
print(next(generator))  # 输出: 4
print(next(generator))  # 输出: 3
 
# 使用 for 循环迭代生成器
for value in generator:
    print(value)  # 输出: 2 1
```
## with关键字
## 函数
```r
def calculate_sector(central_angle,radius):
    sector_area = central_angle / 360 *3.14 *radius**2
    print(f"此扇形面积为：{sector_area}")
    return sector_area
sector_area_1 = calculate_sector(60,20)
```
```r
def calculate_BMI(weighth,heighth):
    BMI = weighth / heighth**2
    if BMI <= 18.5:
        print("您的BMI分类为：偏瘦")
    elif 18.5 < BMI <=25:
        print("您的BMI分类为：正常")
    elif 25< BMI <= 30:
        print("您的BMI分类为：偏胖")
    else:
        print("您的BMI分类为：肥胖")
    return BMI
BMI_1 = calculate_BMI(50,1.8)
print(BMI_1)
```
### 参数
#### 必需参数
```r
#可写函数说明
def printme( str ):
   "打印任何传入的字符串"
   print (str)
   return
 
# 调用 printme 函数，不加参数会报错
printme()
'''
Traceback (most recent call last):
  File "test.py", line 10, in <module>
    printme()
TypeError: printme() missing 1 required positional argument: 'str'
'''
```
#### 关键字参数
```r
def printinfo( name, age ):#name和age就是关键字参数
   print ("名字: ", name)
   print ("年龄: ", age)
   return
 
#调用printinfo函数
printinfo( age=50, name="runoob" )
```
#### 默认参数
```r
def printino( name, age = 35)#age为默认参数
    print("名字:",name)
    print("年龄:",age)
    return
printinfo( age = 50,name = "runoob")
printinfo( name = "runoob"
'''
名字:  runoob
年龄:  50
名字:  runoob
年龄:  35
'''
```
#### 不定长参数
加了星号 ***** 的参数会以元组的形式导入，存放所有未命名的变量参数
```r
def printinfo( arg1, *vartuple ):
   print ("输出: ")
   print (arg1)
   print (vartuple)
printinfo( 70, 60, 50 )
'''
输出: 
70
(60, 50)
'''
```
加了两个星号 ****** 的参数会以字典的形式导入
```r
def printinfo( arg1, **vardict ):
   print ("输出: ")
   print (arg1)
   print (vardict)
printinfo(1, a=2,b=3)
'''
输出: 
1
{'a': 2, 'b': 3}
'''
```
声明函数时，参数中星号 ***** 可以单独出现,如果单独出现星号 *****，则星号 ***** 后的参数必须用关键字传入
```r
def f(a,b,*,c):
    return a+b+c
#参数c要写c=多少
```
#### 匿名函数
## 引入模块
```r
#引入模块的三种方式
import statistics
print(statistics.median([19,-5,36]))
print(statistics.mean([19,-5,36]))

from statistics import median,mean
print(median([19,-5,36]))
print(mean([19,-5,36]))

from statistics import*
print(median([19,-5,36]))
print(mean([19,-5,36]))
```
## 面向对象
## 创建类
```r
class CuteCat:
    def __init__(self,cat_name,cat_age,cat_color):#为新创建的对象设置初始属性
        self.name = cat_name
#self.name 表示给当前这个猫对象设置一个叫做 name 的属性；cat_name 是创建对象时传入的名字参数；这一行的意思是：把传入的 cat_name 保存到当前对象的 name 属性中。
        self.age = cat_age
        self.color = cat_color
    def speak(self):
        print("喵" * self.age)
    def think(self,content):
        print(f"小猫{self.name}在思考{content}")
cat1 = CuteCat("Jojo",2,"橙色")
cat1.think("现在去抓沙发还是去撕纸箱")
print(cat1.name)   # 输出：Jojo
print(cat1.age)    # 输出：2
print(cat1.color)  # 输出：橙色
```
```r
class Student:
    def __init__(self,name,student_id):
        self.name = name
        self.student_id = student_id
        self.grades = {"语文":0,"数学":0,"英语":0}
    def set_grades(self,course,grade):
        if course in self.grades:
            self.grades[course] = grade
    def print_grades(self):
        print(f"学生{self.name}(学号：{self.student_id})的成绩为：")
        for course in self.grades:
            print(f"{course}:{self.grades[course]}分")
chen = Student("小陈",100618)
chen.set_grades("语文",90)
chen.set_grades("数学",91)
chen.set_grades("英语",92)
chen.print_grades()
```
## 类继承
```r

```