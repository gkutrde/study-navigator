class_name =["小明","小红","小白","小蓝","小绿"]
print("自定义班级")
i = 1
for student_name in class_name:
    print(f"{i}. {student_name}")
    i += 1
print(f"共计{len(class_name)}人")
