#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时语音转文字后端服务 - 完全优化版
FastAPI + WebSocket + Whisper
专注于提高准确度和处理质量
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
import re
import psutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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


class OptimizedWhisperProcessor:
    """优化的Whisper处理器，专注于提高准确度"""

    def __init__(self):
        # 智能设备选择
        self.device = self._select_device()
        self.sample_rate = 16000
        self.ffmpeg_available = False

        # 音频时长优化配置
        self.min_audio_duration = 2.0  # 最小时长（秒）
        self.optimal_duration = 3.5  # 最佳时长（秒）
        self.max_audio_duration = 8.0  # 最大时长（秒）
        self.min_audio_size = 25000  # 对应约2.5秒的音频

        # 模型配置
        self.model = None
        self.model_size = self._select_model_size()

        # 繁简转换
        self.converter = None
        self._init_opencc()

        # 性能统计
        self.performance_stats = {
            'total_chunks': 0,
            'successful_transcriptions': 0,
            'avg_processing_time': 0.0,
            'avg_confidence': 0.0,
            'error_count': 0
        }

    def _select_device(self) -> str:
        """智能选择设备"""
        if torch.cuda.is_available():
            gpu_memory = torch.cuda.get_device_properties(0).total_memory
            logger.info(f"检测到GPU，显存: {gpu_memory / 1024 ** 3:.1f}GB")
            return "cuda"
        else:
            logger.info("使用CPU处理")
            return "cpu"

    def _select_model_size(self) -> str:
        """智能选择模型大小"""
        if self.device == "cuda":
            gpu_memory = torch.cuda.get_device_properties(0).total_memory
            if gpu_memory > 12 * 1024 ** 3:  # 12GB+
                return "large-v2"
            elif gpu_memory > 8 * 1024 ** 3:  # 8GB+
                return "large"
            elif gpu_memory > 6 * 1024 ** 3:  # 6GB+
                return "medium"
            elif gpu_memory > 4 * 1024 ** 3:  # 4GB+
                return "small"
            else:
                return "base"
        else:
            cpu_memory = psutil.virtual_memory().total
            cpu_count = psutil.cpu_count()
            if cpu_memory > 16 * 1024 ** 3 and cpu_count >= 8:  # 16GB+ RAM, 8+ cores
                return "medium"
            elif cpu_memory > 8 * 1024 ** 3 and cpu_count >= 4:  # 8GB+ RAM, 4+ cores
                return "small"
            else:
                return "base"

    def _init_opencc(self):
        """初始化繁简转换器"""
        try:
            import opencc
            self.converter = opencc.OpenCC('t2s')
            logger.info("✅ OpenCC繁简转换器已加载")
        except ImportError:
            logger.warning("⚠️ OpenCC未安装，无法进行繁简转换。安装命令: pip install opencc-python-reimplemented")

    async def initialize(self):
        """初始化Whisper模型"""
        try:
            # 检查ffmpeg
            self.ffmpeg_available = check_and_install_ffmpeg()

            logger.info(f"正在加载Whisper模型: {self.model_size} (设备: {self.device})...")

            # 加载模型
            self.model = whisper.load_model(self.model_size, device=self.device)

            # GPU优化
            if self.device == "cuda":
                torch.cuda.empty_cache()
                torch.backends.cudnn.benchmark = True
                # 使用半精度以节省显存（如果支持）
                try:
                    self.model.half()
                    logger.info("✅ 启用半精度模式以节省显存")
                except Exception as e:
                    logger.warning(f"半精度模式启用失败: {e}")

            logger.info(f"✅ Whisper模型加载完成: {self.model_size}")

        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

    async def transcribe_audio_chunk(self, audio_bytes: bytes) -> Optional[Dict]:
        """
        转录单个音频块 - 完全优化版本
        返回包含文本、置信度等信息的字典
        """
        start_time = time.time()
        temp_audio_path = None
        temp_wav_path = None

        try:
            # 提高音频大小阈值
            if len(audio_bytes) < self.min_audio_size:
                logger.debug(f"音频数据太小: {len(audio_bytes)} bytes (需要至少 {self.min_audio_size} bytes)")
                return None

            if not self.ffmpeg_available:
                logger.warning("FFmpeg不可用")
                return None

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(audio_bytes)
                temp_audio_path = f.name
                logger.debug(f"临时音频文件: {temp_audio_path}")

            # 创建WAV输出路径
            temp_wav_path = tempfile.mktemp(suffix='.wav')

            # 优化的FFmpeg转换命令
            cmd = [
                FFMPEG_PATH,
                '-loglevel', 'error',
                '-i', temp_audio_path,
                '-ar', str(self.sample_rate),
                '-ac', '1',
                '-acodec', 'pcm_s16le',
                # 优化的音频滤波器链
                '-af', self._get_optimal_audio_filters(),
                '-f', 'wav',
                '-y',
                temp_wav_path
            ]

            # 执行转换
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15  # 增加超时时间
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg错误: {result.stderr}")
                return None

            # 检查输出文件
            if not os.path.exists(temp_wav_path):
                logger.error("WAV文件未生成")
                return None

            wav_size = os.path.getsize(temp_wav_path)
            if wav_size < 1000:
                logger.warning(f"WAV文件太小: {wav_size} bytes")
                return None

            # 估算音频时长
            estimated_duration = self._estimate_audio_duration(wav_size)
            logger.info(f"处理音频: {wav_size} bytes, 估计时长: {estimated_duration:.1f}s")

            # 语音活动检测
            if not await self._detect_speech_activity(temp_wav_path):
                logger.debug("未检测到语音活动")
                return None

            # 根据音频时长获取优化参数
            transcribe_params = self._get_duration_optimized_params(estimated_duration)

            # 使用Whisper转录
            result = await asyncio.to_thread(
                self.model.transcribe,
                temp_wav_path,
                **transcribe_params
            )

            # 提取结果和置信度
            text = result.get("text", "").strip()
            segments = result.get("segments", [])

            # 计算平均置信度
            avg_confidence = self._calculate_confidence(segments)

            # 后处理文本
            if text:
                text = self._post_process_text(text, estimated_duration)

            # 更新性能统计
            processing_time = time.time() - start_time
            self._update_performance_stats(processing_time, avg_confidence, bool(text))

            if text:
                logger.info(f"✅ 转录成功 ({estimated_duration:.1f}s): {text}")
                return {
                    'text': text,
                    'confidence': avg_confidence,
                    'processing_time': processing_time,
                    'duration': estimated_duration,
                    'segments': len(segments),
                    'language': result.get('language', 'zh')
                }
            else:
                logger.info("转录结果为空")
                return None

        except subprocess.TimeoutExpired:
            logger.error("FFmpeg处理超时")
            return None
        except Exception as e:
            logger.error(f"转录异常: {e}", exc_info=True)
            self.performance_stats['error_count'] += 1
            return None
        finally:
            # 清理临时文件
            for path in [temp_audio_path, temp_wav_path]:
                if path and os.path.exists(path):
                    try:
                        os.unlink(path)
                        logger.debug(f"删除临时文件: {path}")
                    except Exception as e:
                        logger.warning(f"删除文件失败: {path} - {e}")

    def _get_optimal_audio_filters(self) -> str:
        """获取优化的音频滤波器链"""
        filters = [
            "highpass=f=80",  # 高通滤波，移除低频噪音
            "lowpass=f=8000",  # 低通滤波，移除高频噪音
            "loudnorm=I=-16:TP=-1.5:LRA=11",  # 响度标准化
            # 动态范围压缩
            "compand=attacks=0.1:decays=0.3:points=-80/-80|-20/-20|-10/-10|-5/-5|0/-3",
            # 轻微的降噪
            "anlmdn=a=0.0005:b=0.001"
        ]
        return ",".join(filters)

    def _estimate_audio_duration(self, wav_size: int) -> float:
        """估算音频时长"""
        # WAV文件大小估算：16kHz, 16bit, 单声道 ≈ 32KB/秒
        bytes_per_second = self.sample_rate * 2  # 16bit = 2 bytes
        return wav_size / bytes_per_second

    async def _detect_speech_activity(self, audio_path: str) -> bool:
        """语音活动检测"""
        try:
            # 使用FFmpeg检测音量
            cmd = [
                FFMPEG_PATH,
                '-i', audio_path,
                '-af', 'volumedetect',
                '-f', 'null',
                '-'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            # 解析音量信息
            for line in result.stderr.split('\n'):
                if 'mean_volume:' in line:
                    volume_str = line.split('mean_volume:')[1].split('dB')[0].strip()
                    try:
                        mean_volume = float(volume_str)
                        # 如果平均音量太低，认为没有语音
                        return mean_volume > -40.0  # 阈值可调整
                    except ValueError:
                        pass

            return True  # 默认认为有语音

        except Exception as e:
            logger.debug(f"语音活动检测失败: {e}")
            return True

    def _get_duration_optimized_params(self, duration: float) -> dict:
        """根据音频时长优化转录参数"""
        base_params = {
            "language": "zh",
            "task": "transcribe",
            "fp16": False,
            "verbose": False,
            "temperature": 0.0,
            "compression_ratio_threshold": 2.4,
            "no_speech_threshold": 0.6,
            "condition_on_previous_text": False,
            "initial_prompt": "以下是普通话的句子。",
            "suppress_tokens": [-1],
        }

        if duration <= 2.0:
            # 短音频：快速处理
            base_params.update({
                "beam_size": 3,
                "best_of": 3,
                "patience": 0.8,
                "no_speech_threshold": 0.7,
            })
        elif duration <= 4.0:
            # 中等长度：平衡质量和速度（推荐）
            base_params.update({
                "beam_size": 5,
                "best_of": 5,
                "patience": 1.0,
                "no_speech_threshold": 0.6,
                "length_penalty": 1.0,
            })
        elif duration <= 6.0:
            # 较长音频：提高质量
            base_params.update({
                "beam_size": 8,
                "best_of": 8,
                "patience": 1.2,
                "no_speech_threshold": 0.5,
                "length_penalty": 1.1,
                "initial_prompt": "以下是普通话的句子。请准确识别每个词语。",
            })
        else:
            # 很长音频：最高质量设置
            base_params.update({
                "beam_size": 10,
                "best_of": 10,
                "patience": 1.5,
                "no_speech_threshold": 0.4,
                "length_penalty": 1.2,
                "initial_prompt": "以下是普通话的长句子。请仔细识别每个词语，保持语句连贯性。",
            })

        return base_params

    def _calculate_confidence(self, segments: List[Dict]) -> float:
        """计算平均置信度"""
        if not segments:
            return 0.0

        confidences = []
        for segment in segments:
            if 'no_speech_prob' in segment:
                # 转换no_speech_prob为confidence
                confidence = 1.0 - segment['no_speech_prob']
                confidences.append(max(0.0, min(1.0, confidence)))

        return sum(confidences) / len(confidences) if confidences else 0.0

    def _post_process_text(self, text: str, duration: float) -> str:
        """优化的文本后处理"""
        if not text:
            return ""

        # 繁简转换
        if self.converter:
            try:
                text = self.converter.convert(text)
                logger.debug("已转换为简体中文")
            except Exception as e:
                logger.warning(f"繁简转换失败: {e}")

        # 移除多余的空格和换行
        text = ' '.join(text.split())

        # 移除转录标记和无用内容
        unwanted_patterns = [
            r'\[.*?\]',  # 方括号内容
            r'\(.*?\)',  # 圆括号内容（如果是转录标记）
            r'字幕|subtitle',  # 字幕相关词汇
            r'music|♪|♫',  # 音乐标记
            r'\b(嗯|啊|呃)\b',  # 语气词
        ]

        for pattern in unwanted_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # 标点符号规范化
        punctuation_map = {
            '，': '，', '。': '。', '？': '？', '！': '！',
            '；': '；', '：': '：', '"': '"', '"': '"',
            ''': ''': ''': '''
        }

        for old, new in punctuation_map.items():
            text = text.replace(old, new)

        # 对于较长的转录结果，移除重复句子
        if duration > 3.0:
            text = self._remove_duplicate_sentences(text)

        return text.strip()

    def _remove_duplicate_sentences(self, text: str) -> str:
        """移除重复的句子"""
        sentences = [s.strip() for s in text.split('。') if s.strip()]
        unique_sentences = []

        for sentence in sentences:
            # 检查是否与已有句子过于相似
            is_duplicate = False
            for existing in unique_sentences:
                similarity = self._calculate_similarity(sentence, existing)
                if similarity > 0.8:  # 相似度阈值
                    is_duplicate = True
                    # 保留更长的句子
                    if len(sentence) > len(existing):
                        unique_sentences.remove(existing)
                        unique_sentences.append(sentence)
                    break

            if not is_duplicate:
                unique_sentences.append(sentence)

        result = '。'.join(unique_sentences)
        if result and not result.endswith('。'):
            result += '。'

        return result

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        # 简单的字符级相似度计算
        if not text1 or not text2:
            return 0.0

        longer = text1 if len(text1) > len(text2) else text2
        shorter = text2 if len(text1) > len(text2) else text1

        if len(longer) == 0:
            return 1.0

        # 计算编辑距离
        def edit_distance(s1, s2):
            if len(s1) < len(s2):
                s1, s2 = s2, s1

            distances = range(len(s2) + 1)
            for i2, c2 in enumerate(s1):
                distances_ = [i2 + 1]
                for i1, c1 in enumerate(s2):
                    if c1 == c2:
                        distances_.append(distances[i1])
                    else:
                        distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
                distances = distances_
            return distances[-1]

        edit_dist = edit_distance(text1, text2)
        return (len(longer) - edit_dist) / len(longer)

    def _update_performance_stats(self, processing_time: float,
                                  confidence: float, success: bool):
        """更新性能统计"""
        self.performance_stats['total_chunks'] += 1

        if success:
            self.performance_stats['successful_transcriptions'] += 1

            # 更新平均处理时间
            current_avg = self.performance_stats['avg_processing_time']
            total = self.performance_stats['successful_transcriptions']
            self.performance_stats['avg_processing_time'] = \
                (current_avg * (total - 1) + processing_time) / total

            # 更新平均置信度
            current_avg_conf = self.performance_stats['avg_confidence']
            self.performance_stats['avg_confidence'] = \
                (current_avg_conf * (total - 1) + confidence) / total

    def get_performance_stats(self) -> Dict:
        """获取性能统计"""
        total = self.performance_stats['total_chunks']
        success = self.performance_stats['successful_transcriptions']

        return {
            **self.performance_stats,
            'success_rate': success / total if total > 0 else 0.0,
            'error_rate': self.performance_stats['error_count'] / total if total > 0 else 0.0,
            'model_info': {
                'size': self.model_size,
                'device': self.device,
                'ffmpeg_available': self.ffmpeg_available
            }
        }


# 全局处理器
whisper_processor = OptimizedWhisperProcessor()


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
            "transcription_history": [],
            "total_processing_time": 0.0,
            "avg_confidence": 0.0
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
    description="基于Whisper的实时语音识别API - 完全优化版",
    version="5.0.0",
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
    stats = whisper_processor.get_performance_stats()
    return {
        "message": "实时语音转文字服务 - 完全优化版",
        "status": "running",
        "model_info": stats['model_info'],
        "performance": {
            "success_rate": f"{stats['success_rate']:.1%}",
            "avg_confidence": f"{stats['avg_confidence']:.2f}",
            "avg_processing_time": f"{stats['avg_processing_time']:.2f}s"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    ffmpeg_available = check_and_install_ffmpeg()
    stats = whisper_processor.get_performance_stats()

    return {
        "status": "healthy",
        "whisper_loaded": whisper_processor.model is not None,
        "ffmpeg_available": ffmpeg_available,
        "model_size": whisper_processor.model_size,
        "device": whisper_processor.device,
        "active_connections": len(manager.active_connections),
        "performance_stats": stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/stats")
async def get_stats():
    """获取详细统计信息"""
    return whisper_processor.get_performance_stats()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点"""
    client_id = f"client_{int(time.time())}"

    try:
        await manager.connect(websocket, client_id)

        # 发送连接成功消息
        await manager.send_message({
            "type": "connected",
            "message": "连接成功，已启用完全优化模式" if whisper_processor.ffmpeg_available else "连接成功(FFmpeg未安装,语音识别不可用)",
            "client_id": client_id,
            "ffmpeg_available": whisper_processor.ffmpeg_available,
            "model_info": {
                "size": whisper_processor.model_size,
                "device": whisper_processor.device
            }
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
        await handle_optimized_audio_chunk(websocket, message)

    elif message_type == "start_recording":
        conn_data = manager.connection_data.get(websocket)
        if conn_data:
            conn_data["chunk_count"] = 0
            conn_data["transcription_history"] = []
            conn_data["total_processing_time"] = 0.0

        await manager.send_message({
            "type": "recording_started",
            "message": "开始录音...",
            "optimization_enabled": True
        }, websocket)

    elif message_type == "stop_recording":
        await handle_stop_recording(websocket)

    elif message_type == "get_stats":
        stats = whisper_processor.get_performance_stats()
        await manager.send_message({
            "type": "stats",
            "data": stats
        }, websocket)

    elif message_type == "ping":
        await manager.send_message({
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        }, websocket)


async def handle_optimized_audio_chunk(websocket: WebSocket, message: dict):
    """
    处理优化的音频块
    """
    try:
        # 解码Base64音频数据
        audio_base64 = message.get("audio_data", "")
        if not audio_base64:
            logger.warning("音频数据为空")
            return

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

        # 检查音频大小和预估时长
        estimated_duration = len(audio_bytes) / (16000 * 2)  # 粗略估算

        logger.info(f"📦 收到音频块 #{chunk_num}: {len(audio_bytes)} bytes, 预估时长: {estimated_duration:.1f}s")

        # 验证音频大小
        if len(audio_bytes) < whisper_processor.min_audio_size:
            logger.warning(f"音频块 #{chunk_num} 太小，跳过")
            await manager.send_message({
                "type": "processing_status",
                "chunk_number": chunk_num,
                "status": "skipped",
                "reason": f"音频太短 ({estimated_duration:.1f}s < 2.5s)"
            }, websocket)
            return

        # 检查FFmpeg
        if not whisper_processor.ffmpeg_available:
            await manager.send_message({
                "type": "error",
                "message": "FFmpeg未安装，无法进行语音识别"
            }, websocket)
            return

        # 处理音频块
        logger.info(f"🎯 开始处理音频块 #{chunk_num}...")

        # 转录音频
        result = await whisper_processor.transcribe_audio_chunk(audio_bytes)

        if result and result['text']:
            text = result['text']
            confidence = result['confidence']
            processing_time = result['processing_time']

            # 避免重复
            if text != conn_data.get("last_transcription", ""):
                conn_data["last_transcription"] = text
                conn_data["total_transcriptions"] += 1
                conn_data["total_processing_time"] += processing_time

                # 更新平均置信度
                if conn_data["total_transcriptions"] == 1:
                    conn_data["avg_confidence"] = confidence
                else:
                    conn_data["avg_confidence"] = (
                                                          conn_data["avg_confidence"] * (
                                                              conn_data["total_transcriptions"] - 1) + confidence
                                                  ) / conn_data["total_transcriptions"]

                conn_data["transcription_history"].append({
                    "text": text,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "chunk_number": chunk_num,
                    "confidence": confidence,
                    "processing_time": processing_time,
                    "duration": result.get('duration', 0)
                })

                # 立即发送转录结果
                await manager.send_message({
                    "type": "transcription",
                    "text": text,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "chunk_number": chunk_num,
                    "confidence": confidence,
                    "processing_time": processing_time,
                    "audio_duration": result.get('duration', 0),
                    "segments": result.get('segments', 0)
                }, websocket)

                logger.info(f"✨ 音频块 #{chunk_num} 转录成功: {text} (置信度: {confidence:.2f})")
            else:
                logger.info(f"音频块 #{chunk_num} 转录结果重复，跳过")
        else:
            logger.warning(f"音频块 #{chunk_num} 转录结果为空")
            await manager.send_message({
                "type": "processing_status",
                "chunk_number": chunk_num,
                "status": "no_speech",
                "message": "未检测到语音或处理失败"
            }, websocket)

        # 发送处理状态
        await manager.send_message({
            "type": "processing_status",
            "chunk_number": chunk_num,
            "total_chunks": conn_data["chunk_count"],
            "total_transcriptions": conn_data["total_transcriptions"],
            "avg_confidence": conn_data["avg_confidence"],
            "avg_processing_time": conn_data["total_processing_time"] / max(1, conn_data["total_transcriptions"]),
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
                "avg_confidence": conn_data["avg_confidence"],
                "total_processing_time": conn_data["total_processing_time"],
                "timestamp": datetime.now().strftime("%H:%M:%S")
            }, websocket)

        await manager.send_message({
            "type": "recording_stopped",
            "message": "录音已停止",
            "summary": {
                "total_chunks_processed": conn_data["chunk_count"],
                "total_transcriptions": conn_data["total_transcriptions"],
                "avg_confidence": conn_data["avg_confidence"],
                "total_processing_time": conn_data["total_processing_time"]
            }
        }, websocket)

        # 重置计数
        conn_data["chunk_count"] = 0
        conn_data["transcription_history"] = []
        conn_data["total_processing_time"] = 0.0

    except Exception as e:
        logger.error(f"停止录音错误: {e}", exc_info=True)


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🎙️  实时语音转文字服务 v5.0 - 完全优化版")
    print("=" * 80)
    print("🔧 主要优化:")
    print("   • 智能模型选择 (base/small/medium/large)")
    print("   • 优化录音时长 (3.5秒最佳平衡点)")
    print("   • 高级音频预处理 (降噪+响度标准化)")
    print("   • 繁简转换 (OpenCC)")
    print("   • 自适应参数调整")
    print("   • 性能监控和统计")
    print("📌 重要：本服务需要FFmpeg来处理音频")
    print("=" * 80 + "\n")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )