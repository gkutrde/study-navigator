CTF
## 知识体系
- Referer：从哪里来，上一个页面
- User-Agent：浏览器的信息
- robots爬虫文件
- 验证原始来源的ip地址
  - 本地
    - Client-IP: 127.0.0.1
    - Forwarded-For-Ip: 127.0.0.1
    - Forwarded-For: 127.0.0.1, localhost
    - Forwarded: 127.0.0.1, localhost
    - True-Client-IP: 127.0.0.1
    - X-Client-IP: 127.0.0.
    - X-Custom-IP-Authorization: 127.0.0.1
    - X-Forward-For: 127.0.0.1
    - X-Forward: 127.0.0.1, localhost
    - X-Forwarded-By: 127.0.0.1, localhost
    - X-Forwarded-For-Original: 127.0.0.1, localhost
    - X-Forwarded-For: 127.0.0.1, localhost
- MD5
  - MD5概述
    - MD5消息摘要算法，属Hash算法一类。MD5算法对输入任意长度的消息进行运行，产生一个128位的消息摘要（32位的数字字母混合码）
    - 不可逆
  - MD5绕过
    - 弱类型比较绕过
```php
$a != $b
md5($a) == md5($b)
#解题思路
#找到不同的$a和$b，两者的md5值均为0e开头的形式
```
```php
$a != $b
md5($a) === md5($b)
#解题思路
#使$a和$b为两个不同的数组（array），两者的md5值均为null
```
## 内网靶场的虚拟搭建
## 云服务与Docker
### 云服务器
#### 云服务器介绍
一台通过公网访问的虚拟服务器，可以是Windows、Linux系统
### Docker
#### Docker简介
- Docker是什么
Docker是一个开源的应用容器引擎，让开发者可以打包他们的应用以及依赖包到一个可移植的容器中，然后发布到任何流行的Linux机器或Windows机器上，也可以实现虚拟化，容器是完全是完全使用沙盒机制，相互之间不会有任何的接口
- Docker组成部分
Docker Client客户端
Docker Daemon守护进程
Docker Image镜像
Docker Container容器
## 渗透测试网络协议基础
## CTF-Web
### PHP弱类型
#### ===和==比较的区别：
- ===在进行比较的时候，会先判断两种字符串的类型是否相等，再比较
- ==在进行比较的时候，会先将字符串类型转化为相同，再比较
  - 如果比较一个数字和字符串或者比较涉及数字内容的字符串，则字符串会被转化为数值，并且按照数值来进行比较
### SQL注入
### 文件上传
### 文件包含
### 远程命令执行
### 服务端请求伪造
### 跨站脚本攻击
### XML外部实体注入
### NodeJS
### 反序列化