#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
create_file.py - IKun 技能配套工具
功能：将命令行参数带时间戳写入桌面上的 ikun.txt
用法：python create_file.py 你想记录的任何内容
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# ----- 强制控制台输出 UTF-8（解决 Windows 中文乱码）-----
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python 版本较低，使用替换方式
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ----- 检查参数 -----
if len(sys.argv) < 2:
    print("❌ 错误：请提供要写入的内容，例如：")
    print(f"   python {Path(sys.argv[0]).name} 今天学会了唱跳rap篮球")
    sys.exit(1)

# ----- 组装写入内容（所有参数以空格拼接）-----
content = " ".join(sys.argv[1:])

# ----- 生成带时间戳的日志行 -----
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_line = f"[{timestamp}] {content}\n"

# ----- 定位桌面路径 -----
desktop = Path.home() / "Desktop"
target_file = desktop / "ikun.txt"

# ----- 以追加模式写入（文件不存在会自动创建）-----
try:
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(log_line)
    print(f"✅ 写入成功！内容已追加到：{target_file}")
    print(f"📝 本条内容：{content}")
except Exception as e:
    print(f"❌ 写入失败：{e}")
    sys.exit(1)