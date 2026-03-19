#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时语音转文字后端服务 - 终极优化版
FastAPI + WebSocket + Whisper
完全避免WebM拼接问题
"""

import os
import json
import asyncio
import logging
import tempfile
import base64
import time
import subprocess
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
import whisper
import torch
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_and_install_ffmpeg():
    """检查并尝试自动安装ffmpeg"""
    # 方法1: 使用shutil.which查找（最可靠）
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        logger.info(f"✅ FFmpeg 已找到: {ffmpeg_path}")
        global FFMPEG_PATH
        FFMPEG_PATH = ffmpeg_path
        return True

    # 方法2: Windows下尝试多个可能的ffmpeg位置
    ffmpeg_paths = [
        'ffmpeg',  # 系统PATH中
        r'C:\Users\GIGA\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe',  # WinGet安装位置
        r'C:\ffmpeg\bin\ffmpeg.exe',  # 常见安装位置
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
    ]

    # 添加conda环境中的ffmpeg路径
    if 'CONDA_PREFIX' in os.environ:
        conda_ffmpeg = os.path.join(os.environ['CONDA_PREFIX'], 'Library', 'bin', 'ffmpeg.exe')
        ffmpeg_paths.append(conda_ffmpeg)

    for ffmpeg_path in ffmpeg_paths:
        try:
            if os.path.exists(ffmpeg_path):
                # 检查ffmpeg是否可用
                result = subprocess.run([ffmpeg_path, '-version'],
                                        capture_output=True,
                                        text=True)
                if result.returncode == 0:
                    logger.info(f"✅ FFmpeg 已找到: {ffmpeg_path}")
                    FFMPEG_PATH = ffmpeg_path
                    return True
        except (FileNotFoundError, OSError):
            continue

    logger.warning("⚠️ FFmpeg 未在预设路径中找到")
    logger.error("请确保FFmpeg在系统PATH中，或安装在以下位置之一:")
    logger.error("- C:\\ffmpeg\\bin\\")
    logger.error("- 系统PATH环境变量中")
    return False


# 全局变量存储FFmpeg路径
FFMPEG_PATH = 'ffmpeg'


# 在WhisperRealtimeProcessor类中的改进

class WhisperRealtimeProcessor:
    def __init__(self):
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.sample_rate = 16000
        self.ffmpeg_available = False

        # 添加繁简转换工具
        try:
            import opencc
            self.converter = opencc.OpenCC('t2s')  # 繁体转简体
            self.use_opencc = True
        except ImportError:
            self.use_opencc = False
            logger.warning("未安装opencc，无法进行繁简转换。运行: pip install opencc-python-reimplemented")

    async def initialize(self):
        """初始化Whisper模型"""
        try:
            self.ffmpeg_available = check_and_install_ffmpeg()
            logger.info(f"正在加载Whisper模型 (设备: {self.device})...")

            # 使用更大的模型以提高准确性
            model_size = "small"  # 或者 "medium", "large" (根据你的硬件能力)
            if torch.cuda.is_available():
                model_size = "medium"  # GPU可以用更大的模型

            self.model = whisper.load_model(model_size, device=self.device)
            logger.info(f"✅ Whisper模型加载完成: {model_size}")

        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

    async def transcribe_audio_chunk(self, audio_bytes: bytes) -> Optional[str]:
        """转录单个音频块 - 优化版本"""
        temp_audio_path = None
        temp_wav_path = None

        try:
            # 基本验证
            if len(audio_bytes) < 1000:
                logger.warning(f"音频数据太小: {len(audio_bytes)} bytes")
                return None

            if not self.ffmpeg_available:
                logger.warning("FFmpeg不可用")
                return None

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(audio_bytes)
                temp_audio_path = f.name

            temp_wav_path = tempfile.mktemp(suffix='.wav')

            # 优化的FFmpeg转换命令
            cmd = [
                FFMPEG_PATH,
                '-loglevel', 'error',
                '-i', temp_audio_path,
                '-ar', str(self.sample_rate),
                '-ac', '1',
                '-acodec', 'pcm_s16le',
                '-af', 'highpass=f=80,lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11',  # 音频滤波和响度标准化
                '-f', 'wav',
                '-y',
                temp_wav_path
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode != 0:
                logger.error(f"FFmpeg错误: {result.stderr}")
                return None

            if not os.path.exists(temp_wav_path) or os.path.getsize(temp_wav_path) < 100:
                logger.warning("WAV文件生成失败或太小")
                return None

            # 优化的Whisper转录参数
            result = await asyncio.to_thread(
                self.model.transcribe,
                temp_wav_path,
                language="zh",  # 明确指定中文
                task="transcribe",  # 明确指定转录任务
                fp16=False,
                verbose=False,
                temperature=0.0,  # 降低随机性
                compression_ratio_threshold=2.4,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
                # 添加更多优化参数
                beam_size=8,  # 增加束搜索大小
                best_of=5,  # 增加候选数量
                patience=1.0,
                length_penalty=1.0,
                suppress_tokens=[-1],  # 抑制特定token
                initial_prompt="以下是普通话的句子。",  # 添加中文提示
            )

            text = result["text"].strip()

            # 转换繁体到简体
            if text and self.use_opencc:
                text = self.converter.convert(text)

            # 清理文本
            text = self.clean_text(text)

            if text:
                logger.info(f"✅ 转录成功: {text}")
                return text
            else:
                logger.info("转录结果为空")
                return None

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg超时")
            return None
        except Exception as e:
            logger.error(f"转录异常: {e}", exc_info=True)
            return None
        finally:
            # 清理临时文件
            for path in [temp_audio_path, temp_wav_path]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                    except Exception as e:
                        logger.warning(f"删除文件失败: {path} - {e}")

    def clean_text(self, text: str) -> str:
        """清理和规范化文本"""
        if not text:
            return ""

        # 移除多余的空格和换行
        text = ' '.join(text.split())

        # 移除常见的转录错误标记
        unwanted_patterns = [
            r'\[.*?\]',  # 移除方括号内容
            r'\(.*?\)',  # 移除圆括号内容（如果是转录标记）
            r'字幕|subtitle',  # 移除字幕相关词汇
        ]

        import re
        for pattern in unwanted_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # 标点符号规范化
        text = text.replace('，', '，').replace('。', '。').replace('？', '？').replace('！', '！')

        return text.strip()


# 在requirements.txt中添加：
# opencc-python-reimplemented==1.1.6


# 全局处理器
whisper_processor = WhisperRealtimeProcessor()


class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_data: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket, client_id: str = None):
        """建立连接"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_data[websocket] = {
            "client_id": client_id,
            "connected_at": datetime.now(),
            "chunk_count": 0,
            "total_transcriptions": 0,
            "last_transcription": "",
            "transcription_history": []  # 保存所有转录历史
        }
        logger.info(f"✅ 客户端连接: {client_id}")

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            client_data = self.connection_data.pop(websocket, {})
            logger.info(f"❌ 客户端断开: {client_data.get('client_id')}")

    async def send_message(self, message: dict, websocket: WebSocket):
        """发送消息"""
        try:
            await websocket.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("🚀 服务启动中...")

    # 创建必要目录
    os.makedirs("temp", exist_ok=True)

    # 初始化Whisper
    try:
        await whisper_processor.initialize()
        logger.info("✅ 服务启动完成")

        if not whisper_processor.ffmpeg_available:
            logger.warning("=" * 60)
            logger.warning("⚠️  FFmpeg未安装，语音识别功能将无法使用!")
            logger.warning("请按以下步骤安装FFmpeg：")
            logger.warning("1. 访问 https://www.gyan.dev/ffmpeg/builds/")
            logger.warning("2. 下载 ffmpeg-release-essentials.zip")
            logger.warning("3. 解压到 C:\\ffmpeg")
            logger.warning("4. 将 C:\\ffmpeg\\bin 添加到系统PATH环境变量")
            logger.warning("5. 重启命令行并重新运行本程序")
            logger.warning("=" * 60)

    except Exception as e:
        logger.error(f"❌ 服务启动失败: {e}")
        raise

    yield

    # 关闭
    logger.info("🛑 服务关闭中...")


# 创建FastAPI应用
app = FastAPI(
    title="实时语音转文字服务",
    description="基于Whisper的实时语音识别API",
    version="4.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "实时语音转文字服务",
        "status": "running",
        "ffmpeg_available": whisper_processor.ffmpeg_available,
        "device": whisper_processor.device,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    ffmpeg_available = check_and_install_ffmpeg()

    return {
        "status": "healthy",
        "whisper_loaded": whisper_processor.model is not None,
        "ffmpeg_available": ffmpeg_available,
        "device": whisper_processor.device,
        "active_connections": len(manager.active_connections),
        "timestamp": datetime.now().isoformat()
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    client_id = f"client_{int(time.time())}"

    try:
        await manager.connect(websocket, client_id)

        # 发送连接成功消息
        await manager.send_message({
            "type": "connected",
            "message": "连接成功" if whisper_processor.ffmpeg_available else "连接成功(FFmpeg未安装,语音识别不可用)",
            "client_id": client_id,
            "ffmpeg_available": whisper_processor.ffmpeg_available
        }, websocket)

        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)

            await handle_message(websocket, message)

    except WebSocketDisconnect:
        logger.info(f"客户端主动断开: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        manager.disconnect(websocket)


async def handle_message(websocket: WebSocket, message: dict):
    """处理WebSocket消息"""
    message_type = message.get("type")

    if message_type == "audio_chunk":
        # 关键改变：直接处理每个音频块，不累积
        await handle_single_audio_chunk(websocket, message)

    elif message_type == "start_recording":
        conn_data = manager.connection_data.get(websocket)
        if conn_data:
            conn_data["chunk_count"] = 0
            conn_data["transcription_history"] = []

        await manager.send_message({
            "type": "recording_started",
            "message": "开始录音..."
        }, websocket)

    elif message_type == "stop_recording":
        await handle_stop_recording(websocket)

    elif message_type == "ping":
        await manager.send_message({
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        }, websocket)


async def handle_single_audio_chunk(websocket: WebSocket, message: dict):
    """
    处理单个音频块 - 核心处理函数
    每个块独立处理，立即返回结果
    """
    try:
        # 解码Base64音频数据
        audio_base64 = message.get("audio_data", "")
        if not audio_base64:
            logger.warning("音频数据为空")
            return

        # Base64解码
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            logger.error(f"Base64解码失败: {e}")
            return

        # 获取连接数据
        conn_data = manager.connection_data.get(websocket)
        if not conn_data:
            logger.warning("连接数据不存在")
            return

        # 更新计数
        conn_data["chunk_count"] += 1
        chunk_num = conn_data["chunk_count"]

        logger.info(f"📦 收到音频块 #{chunk_num}: {len(audio_bytes)} bytes")

        # 验证音频大小
        if len(audio_bytes) < 1000:
            logger.warning(f"音频块 #{chunk_num} 太小，跳过")
            await manager.send_message({
                "type": "processing_status",
                "chunk_number": chunk_num,
                "status": "skipped",
                "reason": "音频太短"
            }, websocket)
            return

        # 检查FFmpeg
        if not whisper_processor.ffmpeg_available:
            await manager.send_message({
                "type": "error",
                "message": "FFmpeg未安装，无法进行语音识别"
            }, websocket)
            return

        # 直接处理这个音频块
        logger.info(f"🎯 开始处理音频块 #{chunk_num}...")

        # 转录音频
        text = await whisper_processor.transcribe_audio_chunk(audio_bytes)

        if text:
            # 避免重复
            if text != conn_data.get("last_transcription", ""):
                conn_data["last_transcription"] = text
                conn_data["total_transcriptions"] += 1
                conn_data["transcription_history"].append({
                    "text": text,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "chunk_number": chunk_num
                })

                # 立即发送转录结果
                await manager.send_message({
                    "type": "transcription",
                    "text": text,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "chunk_number": chunk_num
                }, websocket)

                logger.info(f"✨ 音频块 #{chunk_num} 转录成功: {text}")
            else:
                logger.info(f"音频块 #{chunk_num} 转录结果重复，跳过")
        else:
            logger.warning(f"音频块 #{chunk_num} 转录结果为空")
            await manager.send_message({
                "type": "processing_status",
                "chunk_number": chunk_num,
                "status": "no_speech",
                "message": "未检测到语音"
            }, websocket)

        # 发送处理状态
        await manager.send_message({
            "type": "processing_status",
            "chunk_number": chunk_num,
            "total_chunks": conn_data["chunk_count"],
            "total_transcriptions": conn_data["total_transcriptions"],
            "status": "completed"
        }, websocket)

    except Exception as e:
        logger.error(f"处理音频块错误: {e}", exc_info=True)
        await manager.send_message({
            "type": "error",
            "message": f"处理错误: {str(e)}"
        }, websocket)


async def handle_stop_recording(websocket: WebSocket):
    """处理停止录音"""
    try:
        conn_data = manager.connection_data.get(websocket)
        if not conn_data:
            return

        # 发送所有转录历史
        if conn_data.get("transcription_history"):
            full_text = " ".join([item["text"] for item in conn_data["transcription_history"]])

            await manager.send_message({
                "type": "full_transcription",
                "text": full_text,
                "history": conn_data["transcription_history"],
                "total_chunks": conn_data["chunk_count"],
                "total_transcriptions": conn_data["total_transcriptions"],
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }, websocket)

        await manager.send_message({
            "type": "recording_stopped",
            "message": "录音已停止",
            "total_chunks_processed": conn_data["chunk_count"],
            "total_transcriptions": conn_data["total_transcriptions"]
        }, websocket)

        # 重置计数
        conn_data["chunk_count"] = 0
        conn_data["transcription_history"] = []

    except Exception as e:
        logger.error(f"停止录音错误: {e}", exc_info=True)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎙️  实时语音转文字服务 v4.0 - 终极优化版")
    print("=" * 60)
    print("📌 重要：本服务需要FFmpeg来处理音频")
    print("📌 核心优化：每个音频块独立处理，避免拼接问题")
    print("=" * 60 + "\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )