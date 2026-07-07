import sys
import os
from datetime import datetime


def main():
    # 强制 stdout 为 utf-8，解决 Windows 中文乱码
    sys.stdout.reconfigure(encoding='utf-8')

    # 检查命令行参数
    args = sys.argv[1:]
    if not args:
        print("错误：请提供写入内容作为命令行参数。")
        print("用法：python create_file.py <内容1> <内容2> ...")
        sys.exit(1)

    # 定位系统桌面
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    file_path = os.path.join(desktop, 'cyh.txt')

    # 构建带时间戳的内容
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content = ' '.join(args)
    line = f"[{timestamp}] {content}\n"

    # 文件存在则追加，不存在则新建
    mode = 'a' if os.path.exists(file_path) else 'w'
    with open(file_path, mode, encoding='utf-8') as f:
        f.write(line)

    print(f"执行成功！内容已写入：{file_path}")
    print(f"写入内容：{line.strip()}")


if __name__ == '__main__':
    main()
