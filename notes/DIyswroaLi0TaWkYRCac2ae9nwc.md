HTML
HTML有一系列标签（元素）来定义文本、图像、链接等等。HTML标签是由尖括号包围的关键字。
标签通常成对出现，包括开始标签（也称为双标签），内容位于这里两个标签之间，比如：
```html
<p>这是一个段落。</p>
```
除了双标签，也存在单标签，例如：
```html
<input type="text">
```
区别：单标签用于没有内容的元素，双标签用于有内容的元素
在VSCode创建好HTML之后直接输入"!"就可以生成文件结构
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HTML练习 </title>
</head>
<body>
 <h1>一级标签</h1>
 <h2>二级标签</h2>
 <h3>三级标签</h3>
 <p>这是一个段落式标签<b>加粗</b>、<i>斜体</i><u>下划线</u><s>删除线</s></p>
 <ul>
    <li>无序列表</li>
 </ul>
 <ol>
    <li>有序列表</li>
 </ol>
 *<table* border="1">
    <tr>
        <TH>列标题1</TH>
        <TH>列标题2</TH>
        <TH>列标题3</TH>
    </tr>
    <tr>
        <TD>元素1</TD>
        <TD>元素2</TD>
        <TD>元素3</TD>
    </tr>
    <tr>
        <TD>元素11</TD>
        <TD>元素21</TD>
        <TD>元素31</TD>
    </tr>
</table>

</body>
</html>
```
## HTML属性
基本语法：
<开始标签 属性名="属性值">
属性名对大小写不敏感，属性值对大小写敏感
## 适用于大多数HTML元素的属性
| 属性 | 描述 |
| --- | --- |
| class | 为HTML元素定义一个或多个类名（类名从样式文件引入） |
| id | 定义元素的唯一id |
| style | 规定元素的行内样式 |
    属性
    描述
    class
    为HTML元素定义一个或多个类名（类名从样式文件引入）
    id
    定义元素的唯一id
    style
    规定元素的行内样式
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HTML属性</title>
</head>
<body>
   <a href="https://www.bilibili.com/video/BV1BT4y1W7Aw?spm_id_from=333.788.player.switch&vd_source=6ee0117d56e03852a9db980c08f5d067&p=5">哔哩哔哩</a> 
   <br>
   <a href="https://www.bilibili.com/video/BV1BT4y1W7Aw?spm_id_from=333.788.player.switch&vd_source=6ee0117d56e03852a9db980c08f5d067&p=5" target="_blank">哔哩哔哩</a>
   <hr>
   <img src="https://storage.moegirl.org.cn/moegirl/commons/b/bc/%E8%8A%B1%E7%81%AB%E7%AB%8B%E7%BB%98.jpg" alt="" width="100" height="200">
   <img src="https://storage.moegirl.org.cn/moegirl/commons/b/bc/%E8%8A%B1%E7.jpg" alt="该图片无法显示">
</body>
</html>
```
## HTML区块
### 块元素和行内元素
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HTML 区块</title>
</head>
<body>
    <div class="nav">
    <a href="#">链接1</a>
    <a href="#">链接2</a>
    <a href="#">链接3</a>
    <a href="#">链接4</a>
    <a href="#">链接5</a>
    </div>
    <div class="content">
      <h1>文章标题</h1>  
      <p>文章内容</p>
      <p>文章内容</p>
      <p>文章内容</p>
      <p>文章内容</p>
    </div>
    <span>这是第1个span标签</span>
    <span>这是第2个span标签</span>
    <span>这是第3个span标签</span>
    <span>这是第4个span标签</span>
    <hr>
    <span>链接点击这里 <a href="#">链接</a></span>
</body>
</html>
```
## HTML表单
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HTML 表单</title>
</head>
<body>
    <form action="">
        <lable>用户名：</lable>
        <input type="text" placeholder="请输入用户名"><br>
        <lable>密码：</lable>
        <input type="password" placeholder="请输入密码"><br>
        <lable for="">性别：</lable>
        <input type="radio" name="gender">男
        <input type="radio" name="gender">女<br>
        <lable for="">爱好：</lable>
        <input type="checkbox" name="hobbies">阅读
        <input type="checkbox" name="hobbies">运动
        <input type="checkbox" name="hobbies">音乐<br>
        <input type="submit" value="上传">
    </form>
</body>
</html>
```