JavaScript
## JavaScript的作用
- 客户端脚本：用于在用户浏览器中执行，实现动态效果和用户交互
- 网页开发：与HTML和CSS协同工作，使得网页具有更强的交互性和动态性
- 后端开发：使用Node.js，JavaScript也可以在服务器端运行，实现服务器端应用的开发
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JavaScipt 导入方式</title>
    <script>
        console.log("Hello, Head标签内联样式");
    </script>
    <script src="./js/myscipt.js"></script>
</head>
<body>
    <h1>JavaScript 导入方式</h1>
    <script>
        console.log("Hello, Body标签内联样式");
        alert("你好, 内联样式弹窗");
    </script>
</body>
</html>
```