# FFmpeg安装指南 (Windows系统)

FFmpeg是实时语音转文字系统的必要依赖，用于音频格式转换和处理。以下是详细的安装步骤：

## 1. 下载FFmpeg

1. 访问FFmpeg官方下载页面：https://www.gyan.dev/ffmpeg/builds/
2. 在"release builds"部分，下载最新的`ffmpeg-release-essentials.zip`文件
   - 这是包含基本功能的最小版本，适合我们的项目使用

## 2. 解压FFmpeg

1. 下载完成后，右键点击ZIP文件，选择"解压到指定文件夹"
2. 建议将其解压到`C:\ffmpeg`目录下
3. 解压后，FFmpeg的可执行文件应该位于`C:\ffmpeg\bin`目录中

## 3. 配置环境变量

### 方法一：图形界面配置

1. 右键点击"此电脑"或"我的电脑"，选择"属性"
2. 点击"高级系统设置"
3. 在"系统属性"窗口中，点击"环境变量..."
4. 在"系统变量"部分，找到并双击"Path"
5. 点击"新建"，然后输入`C:\ffmpeg\bin`
6. 点击"确定"保存所有更改

### 方法二：命令行配置

1. 以管理员身份打开命令提示符
2. 运行以下命令：
   ```cmd
   setx /M PATH "%PATH%;C:\ffmpeg\bin"
   ```

## 4. 验证安装

1. 关闭所有打开的命令提示符窗口
2. 重新打开一个新的命令提示符
3. 运行以下命令：
   ```cmd
   ffmpeg -version
   ```
4. 如果看到FFmpeg的版本信息，则表示安装成功

## 5. 重新启动项目

安装完成后，重新运行项目：
```cmd
python main.py
```

## 替代安装方法

### 使用WinGet（Windows 10/11内置包管理器）

1. 以管理员身份打开PowerShell
2. 运行以下命令：
   ```powershell
   winget install --id Gyan.FFmpeg -e
   ```

### 使用Chocolatey

1. 以管理员身份打开命令提示符
2. 运行以下命令：
   ```cmd
   choco install ffmpeg
   ```

## 常见问题

1. **找不到FFmpeg命令**：
   - 确保环境变量配置正确
   - 重新启动命令提示符或计算机

2. **权限错误**：
   - 确保以管理员身份运行命令提示符
   - 检查FFmpeg目录的权限设置

3. **项目仍然无法找到FFmpeg**：
   - 确保FFmpeg版本兼容（建议使用最新版本）
   - 检查项目代码中的FFmpeg路径配置
