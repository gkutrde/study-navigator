CSS
## CSS语法
CSS通常由选择器、属性、和属性值组成，多个规则可以组合在一起，以便使用多个样式。
```html
选择器{
    属性1：属性值1;
    属性2：属性值;
}
```
1. 选择器的声明中可以写无数条属性
2. 声明的每一行属性，都需要以英文分号结尾
3. 声明的所有属性和值都是以键值对这种形式出现的
示例：
```html
p{
    color:blue;
    font-size:16px;
}
```
## CSS的三种导入方式
4. 内联样式
5. 内部样式表
6. 外部样式表
三种导入方式的优先级：内联样式＞内部样式表＞外部样式表
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSS导入方式</title>
    <link rel="stylesheet" href="css/style.css">
    <style>
        p{
            color: blue;
            font-size: 26px;
        }
        h2{
            color: green;
            font-size: 20px;
        }
    </style>
</head>

<body>
    <p>这是应用了CSS样式的文本</p>
    <h1 style="color: red;">这是一个一级标题，使用内联样式</h1>
    <h2 >这是一个二级标题，使用内部样式</h2>
    <h3 >这是一个三级标题，使用外部样式</h3>
</body>
</html>
```
## 选择器
- 元素选择器
- 类选择器
- ID选择器
- 通用选择器
- 子元素选择器
- 后代选择器（包含选择器）
- 相邻元素选择器（兄弟选择器）
- 伪类选择器
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSS选择器</title>
    <style>
    /* 元素选择器 */
    h2{ color: blue;}
    /* 类选择器 */
    .hilight{ background-color: yellow;}
    /* ID选择器 */
    #hider{
        font-size: larger;
    }
    /* 通用选择器 */
    *{font-family: "kaiti";}
    /* 子元素选择器 */
    .father > .son{ color: green;}
    /* 后代选择器 */
    .father p{ 
        color: red;
        font-size: larger;}
        /* 相邻元素选择器 */
    h3 + p{ color: orange;}
    /* 伪类选择器 */
    #element:hover{ color: purple;}
    </style>
</head>
<body>
    <h1>不同类型的选择器</h1>
    <h2>这是一个元素选择器示例</h2>
    <h3 class="hilight">这是一个类选择器示例</h3>
    <h3>这是另一个类选择器示例</h3>
    <h4 id="hider">这是一个ID选择器示例</h4>
    <div class="father">
        <p class="son">这是一个子元素选择器示例</p>
        <div>
            <p class="grandson">这是一个后代选择器示例</p>
        </div>
    </div>
    <p>这是一个普通的p标签</p>    
    <h3>这是一个相邻元素选择器示例</h3>    
    <p>这是一个另一个p标签</p>
    <h3 id="element">这是一个伪类选择器</h3>
</body>
</html>
```
## CSS属性
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSS常用属性</title>
    <style>
        .block{
            background-color: yellow;
            width: 200px;
            height: 100px;
        }
        .inline{
            background-color: green;
        }
        .block-inline{
            width: 200px;
            height: 100px;
        }

    </style>
</head>
<body>
    <h1 style="font: bolder 50px 'kaiti' ;">这是一个font复合属性</h1>
    <p style="line-height: 40px;">这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本这是一段长文本</p>

    <div class="block">这是一个块元素</div>
    <span class="inline">这是一个行内元素</span>
    <img src="https://storage.moegirl.org.cn/moegirl/commons/b/bc/%E8%8A%B1%E7%81%AB%E7%AB%8B%E7%BB%98.jpg" alt="图片" class="block-inline">
    <div style="display: inline; background-color: red;">这是一个转化为行内元素的div标签</div>
</body>
</html>
```
## 盒子模型
[图片]
| 属性名 | 说明 |
| --- | --- |
| 内容（Content） | 盒子包含的实际内容，比如文本、图片等 |
| 内边距（Padding） | 围绕在内容的内部，是内容与边框之间的空间。可以用'padding'属性来设置 |
| 边框（Border） | 围绕在内边距的外部，是盒子的边界。可以用'border'属性来设置 |
| 外边距（Margin） | 围绕在边框外部，是盒子与其他元素之间的空间。可以用'margin'属性来设置 |
    属性名
    说明
    内容（Content）
    盒子包含的实际内容，比如文本、图片等
    内边距（Padding）
    围绕在内容的内部，是内容与边框之间的空间。可以用'padding'属性来设置
    边框（Border）
    围绕在内边距的外部，是盒子的边界。可以用'border'属性来设置
    外边距（Margin）
    围绕在边框外部，是盒子与其他元素之间的空间。可以用'margin'属性来设置
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSS盒子模型</title>
    <style>
        .demo {
            background-color: aqua;
            display: inline-block;
            border: 5px  solid red;
            padding: 20px;
            margin: 100px;
        }
        .border-demo {
            background-color: yellow;
            width: 300px;
            height: 100px;
            border-style: solid dashed dotted double;
            border-width: 10px 6px 20px 50px;
            border-color: red green blue;
        }
        </style>
</head>
<body>
    <div class="demo">你好</div>
    <div class="border-demo">这是一个边框演示</div>
</body>
</html>
```
## 传统网页布局方式
- 标准式（普通流、文档流）：网页按照元素的书写顺序依次排列
- 浮动
- 定位
- 'Flexbox'和'Grid'（自适应布局）
## 浮动
语法：
```html
选择器{
    float: left/right/none;
}
```
注意：浮动是相对于父元素浮动，只会在父元素内部移动
## 浮动的三大特性
- 脱标：脱离标准流
- 一行显示，顶部对齐
- 具备行内块元素特性
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSS浮动</title>
    <style>
        .father {
            background-color: aqua;
            border: 5px solid red;
            overflow: hidden;
        }
        .left-son {
            background-color: red;
            width: 200px;
            height: 100px; 
            float: left;
        }
        .right-son {
            background-color: yellow;
            width: 200px;
            height: 100px;
            float: right;
        }
        </style>
</head>
<body>
    <div class="father">
        <div class="left-son">左浮动</div>
        <div class="right-son">右浮动</div>
    </div>
     <p>这是段文本</p>
</body>
</html>
```
## 定位
- 相对定位：相对于元素在文档流中的正常位置进行定位
- 相对定位：相对于其最近的已定位的祖先元素进行定位，不占据文档流
- 固定定位：相对于浏览器进行定位。不占据文档流，固定在屏幕上的位置，不随滚动而滚动
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>定位</title>
</head>
    <style>
        .box1{
            height: 350px;
            background-color: aqua;
        }
        .box-normal{
            width:100px;
            height: 100px;
            background-color: purple;
        }
        .box-relative{
            width:100px;
            height: 100px;
            background-color: red;
            position: relative;
            top: 50px;
            left: 50px;
        }
        .box2{
            height: 350px;
            background-color: aqua;
            margin-bottom: 400px;
        }
        .box-absolute{
            width:100px;
            height: 100px;
            background-color: yellowgreen;
            position: absolute;
            top: 550px;
            left: 50px;
        }
        .box-fixed{
            width:100px;
            height: 100px;
            background-color: brown;
            position: fixed;
            top: 50px;
            right: 0
        }
    </style>
<body>
    <h1>相对定位</h1>
    <div class="box1">
        <div class="box-normal"></div>
        <div class="box-relative"></div>
        <div class="box-normal"></div>
    </div>
    <h1>绝对定位</h1>
    <div class="box2">
        <div class="box-normal"></div>
        <div class="box-absolute"></div>
        <div class="box-normal"></div>  
    </div>
    <h1>固定定位</h1>
    <div class="box3">    
        <div class="box-fixed"></div>
    </div>
</body>
</html>
```