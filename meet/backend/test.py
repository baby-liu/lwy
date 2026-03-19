#!/usr/bin/env python3
"""
测试FFmpeg安装和路径配置
"""

import os
import sys
import subprocess
import shutil


def test_ffmpeg():
    print("=" * 60)
    print("FFmpeg 检测工具")
    print("=" * 60)

    # 方法1: 使用which/where命令查找
    print("\n1. 使用系统命令查找FFmpeg:")
    if sys.platform == "win32":
        try:
            result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True, shell=True)
            if result.returncode == 0:
                print(f"✅ 找到 FFmpeg: {result.stdout.strip()}")
            else:
                print("❌ where命令未找到ffmpeg")
        except Exception as e:
            print(f"❌ where命令失败: {e}")

    # 方法2: 使用shutil.which
    print("\n2. 使用shutil.which查找:")
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ 找到 FFmpeg: {ffmpeg_path}")
    else:
        print("❌ shutil.which未找到ffmpeg")

    # 方法3: 直接运行ffmpeg
    print("\n3. 直接运行ffmpeg -version:")
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg可以正常运行")
            print(f"版本信息: {result.stdout.splitlines()[0]}")
        else:
            print(f"❌ FFmpeg运行失败: {result.stderr}")
    except FileNotFoundError:
        print("❌ FFmpeg命令未找到")
    except Exception as e:
        print(f"❌ 运行错误: {e}")

    # 方法4: 在conda环境中运行
    print("\n4. 检查conda环境:")
    if 'CONDA_PREFIX' in os.environ:
        print(f"当前conda环境: {os.environ['CONDA_PREFIX']}")
        conda_ffmpeg = os.path.join(os.environ['CONDA_PREFIX'], 'Library', 'bin', 'ffmpeg.exe')
        if os.path.exists(conda_ffmpeg):
            print(f"✅ 在conda环境中找到ffmpeg: {conda_ffmpeg}")
        else:
            print("❌ conda环境中未找到ffmpeg")
    else:
        print("❌ 未激活conda环境")

    # 方法5: 检查常见安装路径
    print("\n5. 检查常见安装路径:")
    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
        r'C:\Tools\ffmpeg\bin\ffmpeg.exe',
    ]

    for path in common_paths:
        if os.path.exists(path):
            print(f"✅ 找到: {path}")
        else:
            print(f"❌ 不存在: {path}")

    # 显示系统PATH
    print("\n6. 系统PATH环境变量:")
    path_dirs = os.environ.get('PATH', '').split(os.pathsep)
    print("PATH中包含以下目录:")
    for i, dir_path in enumerate(path_dirs[:10], 1):  # 只显示前10个
        print(f"  {i}. {dir_path}")
        # 检查这个目录中是否有ffmpeg
        if os.path.exists(dir_path):
            ffmpeg_exe = os.path.join(dir_path, 'ffmpeg.exe')
            if os.path.exists(ffmpeg_exe):
                print(f"     ✅ 包含ffmpeg.exe")

    print("\n" + "=" * 60)
    print("建议:")
    if ffmpeg_path or shutil.which('ffmpeg'):
        print("✅ FFmpeg已正确安装并在PATH中")
        print("如果Python仍无法找到，尝试:")
        print("1. 重启IDE/编辑器")
        print("2. 重新激活conda环境")
        print("3. 使用完整路径调用ffmpeg")
    else:
        print("❌ FFmpeg未在系统PATH中")
        print("请确保:")
        print("1. FFmpeg已安装")
        print("2. FFmpeg的bin目录已添加到系统PATH")
        print("3. 重启命令行窗口")
    print("=" * 60)


if __name__ == "__main__":
    test_ffmpeg()