<template>
  <div class="container">
    <!-- 头部 -->
    <div class="header">
      <h1>🎤 实时语音转文字</h1>
      <p>基于Whisper的实时语音识别系统 - 完全优化版</p>
      <div class="version-info">
        <span v-if="modelInfo.size">模型: {{ modelInfo.size }}</span>
        <span v-if="modelInfo.device">设备: {{ modelInfo.device }}</span>
      </div>
    </div>
    
    <!-- 状态栏 -->
    <div class="status-bar">
      <div class="status-item">
        <div class="status-dot" :class="connectionStatus"></div>
        <span>连接状态: {{ connectionStatusText }}</span>
      </div>
      <div class="status-item">
        <div class="status-dot" :class="{ recording: isRecording }"></div>
        <span>录音状态: {{ recordingStatusText }}</span>
      </div>
      <div class="status-item">
        <span>⏱️ 录音时长: {{ recordingDuration }}s</span>
      </div>
      <div class="status-item">
        <span>📊 音频块数: {{ chunkCount }}</span>
      </div>
      <div class="status-item">
        <span>🎯 成功率: {{ successRate }}</span>
      </div>
      <div class="status-item">
        <span>⚡ 平均置信度: {{ avgConfidence }}</span>
      </div>
    </div>
    
    <!-- 控制面板 -->
    <div class="control-panel">
      <button 
        class="record-button"
        :class="recordButtonClass"
        @click="toggleRecording"
        :disabled="!isConnected"
      >
        {{ recordButtonIcon }}
      </button>
      
      <div class="action-buttons">
        <button 
          class="btn btn-primary" 
          @click="connectWebSocket"
          :disabled="isConnected"
        >
          {{ isConnected ? '已连接' : '连接服务' }}
        </button>
        <button 
          class="btn btn-secondary" 
          @click="clearTranscriptions"
        >
          清空记录
        </button>
        <button 
          class="btn btn-secondary" 
          @click="downloadTranscript"
          :disabled="transcriptions.length === 0"
        >
          下载文本
        </button>
        <button 
          class="btn btn-info" 
          @click="getStats"
          :disabled="!isConnected"
        >
          获取统计
        </button>
      </div>
    </div>
    
    <!-- 音频可视化 -->
    <div class="audio-visualizer" v-if="isRecording">
      <div 
        class="bar" 
        v-for="(height, index) in visualizerBars" 
        :key="index"
        :style="{ height: height + 'px' }"
      ></div>
    </div>
    
    <!-- 主要内容 -->
    <div class="main-content">
      <!-- 转录结果 -->
      <div class="panel">
        <h3>📝 转录结果</h3>
        <div class="transcription-area" ref="transcriptionArea">
          <div v-if="transcriptions.length === 0" class="empty-state">
            <div class="icon">🎙️</div>
            <p>点击录音按钮开始语音转文字...</p>
            <p class="optimization-note">已启用完全优化模式 (3.5秒时长 + 智能模型)</p>
          </div>
          <div 
            v-for="(item, index) in transcriptions" 
            :key="index"
            class="transcription-item"
            :class="{ 'high-confidence': item.confidence > 0.8, 'low-confidence': item.confidence < 0.5 }"
          >
            <div class="item-header">
              <div class="timestamp">{{ item.timestamp }}</div>
              <div class="confidence-badge" :class="getConfidenceClass(item.confidence)">
                置信度: {{ (item.confidence * 100).toFixed(0) }}%
              </div>
              <div class="processing-time">{{ item.processing_time?.toFixed(2) }}s</div>
            </div>
            <div class="text-content">{{ item.text }}</div>
            <div class="item-footer" v-if="item.audio_duration">
              <span>音频时长: {{ item.audio_duration?.toFixed(1) }}s</span>
              <span v-if="item.segments">分段: {{ item.segments }}</span>
            </div>
          </div>
        </div>
        
        <!-- 统计信息 -->
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ transcriptions.length }}</div>
            <div class="stat-label">转录段落</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ totalWords }}</div>
            <div class="stat-label">总字数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ avgConfidence }}</div>
            <div class="stat-label">平均置信度</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ avgProcessingTime }}s</div>
            <div class="stat-label">平均处理时间</div>
          </div>
        </div>
      </div>
      
      <!-- 系统日志 -->
      <div class="panel">
        <h3>📊 系统日志</h3>
        <div class="log-area" ref="logArea">
          <div 
            v-for="(log, index) in logs" 
            :key="index"
            class="log-entry"
            :class="log.level"
          >
            <span class="log-timestamp">{{ log.timestamp }}</span>
            <span class="log-level" :class="log.level">{{ log.level.toUpperCase() }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 性能监控面板 -->
    <div class="performance-panel" v-if="performanceStats">
      <h4>⚡ 性能监控</h4>
      <div class="performance-grid">
        <div class="perf-item">
          <span class="perf-label">总处理块数:</span>
          <span class="perf-value">{{ performanceStats.total_chunks }}</span>
        </div>
        <div class="perf-item">
          <span class="perf-label">成功转录:</span>
          <span class="perf-value">{{ performanceStats.successful_transcriptions }}</span>
        </div>
        <div class="perf-item">
          <span class="perf-label">成功率:</span>
          <span class="perf-value">{{ (performanceStats.success_rate * 100).toFixed(1) }}%</span>
        </div>
        <div class="perf-item">
          <span class="perf-label">错误率:</span>
          <span class="perf-value">{{ (performanceStats.error_rate * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

export default {
  name: 'OptimizedSoundRecognition',
  setup() {
    // 响应式数据
    const isConnected = ref(false)
    const isRecording = ref(false)
    const websocket = ref(null)
    const audioStream = ref(null)
    const transcriptions = ref([])
    const logs = ref([])
    const recordingStartTime = ref(null)
    const recordingDuration = ref(0)
    const chunkCount = ref(0)
    const visualizerBars = ref(Array(50).fill(10))
    const modelInfo = ref({})
    const performanceStats = ref(null)
    
    // 优化配置
    const OPTIMAL_CHUNK_DURATION = 3500  // 3.5秒最佳时长
    const MIN_AUDIO_SIZE = 25000          // 最小音频大小
    const OVERLAP_DURATION = 500          // 重叠时间
    const MAX_AUDIO_SIZE = 10000000       // 最大音频大小
    
    // 录音控制变量
    let recordingInterval = null
    let durationTimer = null
    let audioContext = null
    
    // DOM引用
    const transcriptionArea = ref(null)
    const logArea = ref(null)
    
    // 计算属性
    const connectionStatus = computed(() => 
      isConnected.value ? 'connected' : 'disconnected'
    )
    
    const connectionStatusText = computed(() => 
      isConnected.value ? '已连接' : '未连接'
    )
    
    const recordingStatusText = computed(() => 
      isRecording.value ? '录音中' : '待录音'
    )
    
    const recordButtonClass = computed(() => {
      if (isRecording.value) return 'recording'
      return 'idle'
    })
    
    const recordButtonIcon = computed(() => {
      if (isRecording.value) return '⏹️'
      return '🎙️'
    })
    
    const totalWords = computed(() => {
      return transcriptions.value.reduce((total, item) => {
        return total + (item.text?.length || 0)
      }, 0)
    })
    
    const successRate = computed(() => {
      if (chunkCount.value === 0) return '0%'
      const rate = (transcriptions.value.length / chunkCount.value) * 100
      return `${rate.toFixed(1)}%`
    })
    
    const avgConfidence = computed(() => {
      if (transcriptions.value.length === 0) return '0%'
      const total = transcriptions.value.reduce((sum, item) => sum + (item.confidence || 0), 0)
      const avg = total / transcriptions.value.length
      return `${(avg * 100).toFixed(1)}%`
    })
    
    const avgProcessingTime = computed(() => {
      if (transcriptions.value.length === 0) return '0.0'
      const total = transcriptions.value.reduce((sum, item) => sum + (item.processing_time || 0), 0)
      const avg = total / transcriptions.value.length
      return avg.toFixed(2)
    })
    
    // WebSocket连接
    const connectWebSocket = async () => {
      try {
        // 先测试后端是否可达
        await testBackendConnection()
        
        const wsUrl = 'ws://localhost:8000/ws'
        addLog('info', `正在连接WebSocket: ${wsUrl}`)
        
        websocket.value = new WebSocket(wsUrl)
        
        // 设置连接超时
        const connectionTimeout = setTimeout(() => {
          if (websocket.value && websocket.value.readyState === WebSocket.CONNECTING) {
            websocket.value.close()
            addLog('error', 'WebSocket连接超时')
          }
        }, 5000)
        
        websocket.value.onopen = () => {
          clearTimeout(connectionTimeout)
          isConnected.value = true
          addLog('info', 'WebSocket连接成功')
        }
        
        websocket.value.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            handleWebSocketMessage(data)
          } catch (error) {
            addLog('error', `消息解析失败: ${error.message}`)
          }
        }
        
        websocket.value.onclose = (event) => {
          clearTimeout(connectionTimeout)
          isConnected.value = false
          addLog('warning', `WebSocket连接关闭: ${event.code} - ${event.reason}`)
        }
        
        websocket.value.onerror = (error) => {
          clearTimeout(connectionTimeout)
          addLog('error', `WebSocket连接错误: ${error.type || 'Unknown error'}`)
        }
        
      } catch (error) {
        addLog('error', `连接准备失败: ${error.message}`)
      }
    }
    
    // 测试后端连接
    const testBackendConnection = async () => {
      try {
        const response = await fetch('http://localhost:8000/health')
        if (!response.ok) {
          throw new Error(`后端服务响应错误: ${response.status}`)
        }
        const data = await response.json()
        addLog('info', `后端服务状态: ${data.status}`)
        if (data.model_size) {
          modelInfo.value = {
            size: data.model_size,
            device: data.device
          }
        }
        return true
      } catch (error) {
        addLog('error', `后端服务不可达: ${error.message}`)
        throw error
      }
    }
    
    // 处理WebSocket消息
    const handleWebSocketMessage = (message) => {
      const { type, ...data } = message
      
      switch (type) {
        case 'connected':
          addLog('info', data.message)
          if (data.model_info) {
            modelInfo.value = data.model_info
          }
          break
          
        case 'transcription':
          addTranscription(data.text, data.timestamp, data)
          addLog('info', `转录: ${data.text} (置信度: ${(data.confidence * 100).toFixed(0)}%)`)
          break
          
        case 'processing_status':
          if (data.status === 'skipped') {
            addLog('warning', `块 #${data.chunk_number}: ${data.reason || data.message}`)
          } else if (data.status === 'no_speech') {
            addLog('debug', `块 #${data.chunk_number}: ${data.message}`)
          }
          break
          
        case 'recording_started':
          addLog('info', data.message)
          break
          
        case 'recording_stopped':
          addLog('info', data.message)
          if (data.summary) {
            addLog('info', `录音总结: 处理${data.summary.total_chunks_processed}块, 成功${data.summary.total_transcriptions}次`)
          }
          break
          
        case 'full_transcription':
          addLog('info', `完整转录完成，共${data.total_transcriptions}段`)
          break
          
        case 'stats':
          performanceStats.value = data.data
          addLog('info', '性能统计已更新')
          break
          
        case 'error':
          addLog('error', data.message)
          break
          
        case 'pong':
          // 心跳响应
          break
          
        default:
          addLog('info', `未知消息类型: ${type}`)
      }
    }
    
    // 开始/停止录音
    const toggleRecording = async () => {
      if (isRecording.value) {
        await stopRecording()
      } else {
        await startRecording()
      }
    }
    
    // 开始录音 - 完全优化版
    const startRecording = async () => {
      try {
        // 检查浏览器支持
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error('浏览器不支持录音功能')
        }
        
        // 优化的音频约束
        const audioConstraints = {
          audio: {
            sampleRate: 16000,           // Whisper推荐的采样率
            channelCount: 1,             // 单声道
            echoCancellation: true,       // 回声消除
            noiseSuppression: true,       // 噪音抑制
            autoGainControl: true,        // 自动增益控制
            googEchoCancellation: true,   // Google回声消除
            googAutoGainControl: true,    // Google自动增益
            googNoiseSuppression: true,   // Google噪音抑制
            googHighpassFilter: true,     // Google高通滤波
            googAudioMirroring: false,    // 关闭音频镜像
            latency: 0.01,               // 低延迟
            volume: 1.0                  // 音量
          }
        }
        
        // 获取麦克风权限
        audioStream.value = await navigator.mediaDevices.getUserMedia(audioConstraints)
        
        // 设置录音状态
        isRecording.value = true
        recordingStartTime.value = Date.now()
        chunkCount.value = 0
        
        // 通知服务器开始录音
        if (websocket.value?.readyState === WebSocket.OPEN) {
          websocket.value.send(JSON.stringify({
            type: 'start_recording'
          }))
        }
        
        // 开始音频可视化
        startAudioVisualization()
        
        // 开始计时
        startRecordingTimer()
        
        // 开始优化的循环录音
        startOptimizedCyclicRecording()
        
        addLog('info', `开始录音 (优化模式: ${OPTIMAL_CHUNK_DURATION/1000}s时长)`)
        
      } catch (error) {
        addLog('error', `录音启动失败: ${error.message}`)
        if (error.name === 'NotAllowedError') {
          addLog('error', '请在浏览器中允许麦克风权限')
        } else if (error.name === 'NotFoundError') {
          addLog('error', '未找到麦克风设备')
        } else if (error.name === 'NotReadableError') {
          addLog('error', '麦克风被其他应用占用')
        }
      }
    }
    
    // 优化的循环录音方法
    const startOptimizedCyclicRecording = () => {
      const createAndStartRecorder = () => {
        if (!isRecording.value || !audioStream.value) {
          return
        }
        
        try {
          // 选择最佳音频格式
          let mimeType = 'audio/webm;codecs=opus'
          if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'audio/webm'
            if (!MediaRecorder.isTypeSupported(mimeType)) {
              mimeType = 'audio/wav'
            }
          }
          
          // 创建新的MediaRecorder，使用高比特率
          const recorder = new MediaRecorder(audioStream.value, {
            mimeType,
            bitsPerSecond: 256000  // 高比特率保证音质
          })
          
          const audioChunks = []
          
          // 收集音频数据
          recorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
              audioChunks.push(event.data)
            }
          }
          
          // 录音停止时发送完整的音频文件
          recorder.onstop = async () => {
            if (audioChunks.length === 0) return
            
            // 合并为完整的音频文件
            const audioBlob = new Blob(audioChunks, { type: mimeType })
            
            // 音频质量检查
            if (audioBlob.size < MIN_AUDIO_SIZE) {
              addLog('warning', `音频片段太短 (${Math.round(audioBlob.size/1000)}KB < ${Math.round(MIN_AUDIO_SIZE/1000)}KB)，跳过`)
              return
            }
            
            if (audioBlob.size > MAX_AUDIO_SIZE) {
              addLog('warning', '音频片段过大，可能有问题')
              return
            }
            
            // 音频质量验证
            if (await validateAudioQuality(audioBlob)) {
              const reader = new FileReader()
              reader.onload = () => {
                try {
                  const arrayBuffer = reader.result
                  const uint8Array = new Uint8Array(arrayBuffer)
                  const base64Audio = btoa(String.fromCharCode.apply(null, uint8Array))
                  
                  // 发送到服务器
                  if (websocket.value?.readyState === WebSocket.OPEN) {
                    websocket.value.send(JSON.stringify({
                      type: 'audio_chunk',
                      audio_data: base64Audio,
                      format: mimeType,
                      timestamp: Date.now(),
                      duration: OPTIMAL_CHUNK_DURATION,
                      chunk_id: chunkCount.value + 1
                    }))
                    
                    chunkCount.value++
                    addLog('info', `发送优化音频块 #${chunkCount.value} (${Math.round(audioBlob.size/1000)}KB, ${OPTIMAL_CHUNK_DURATION/1000}s)`)
                  }
                } catch (error) {
                  addLog('error', `音频发送失败: ${error.message}`)
                }
              }
              reader.readAsArrayBuffer(audioBlob)
            } else {
              addLog('warning', '音频质量不达标，跳过')
            }
          }
          
          recorder.onerror = (event) => {
            addLog('error', `录音器错误: ${event.error}`)
          }
          
          // 开始录音
          recorder.start()
          
          // 3.5秒后停止这个recorder
          setTimeout(() => {
            if (recorder.state === 'recording') {
              recorder.stop()
            }
          }, OPTIMAL_CHUNK_DURATION)
          
        } catch (error) {
          addLog('error', `创建录音器失败: ${error.message}`)
        }
      }
      
      // 立即开始第一次录音
      createAndStartRecorder()
      
      // 每3秒创建新的录音器（有重叠以避免遗漏）
      recordingInterval = setInterval(() => {
        if (isRecording.value) {
          createAndStartRecorder()
        } else {
          clearInterval(recordingInterval)
        }
      }, OPTIMAL_CHUNK_DURATION - OVERLAP_DURATION)
    }
    
    // 音频质量验证函数
    const validateAudioQuality = async (audioBlob) => {
      return new Promise((resolve) => {
        // 基础大小检查
        if (audioBlob.size < MIN_AUDIO_SIZE || audioBlob.size > MAX_AUDIO_SIZE) {
          resolve(false)
          return
        }
        
        // 简单的音频头部验证
        const reader = new FileReader()
        reader.onload = () => {
          const arrayBuffer = reader.result
          const view = new DataView(arrayBuffer)
          
          // 检查WebM文件头
          if (arrayBuffer.byteLength >= 4) {
            const header = new Uint8Array(arrayBuffer.slice(0, 4))
            // WebM文件头通常以EBML开始
            resolve(header[0] === 0x1a && header[1] === 0x45 && header[2] === 0xdf && header[3] === 0xa3)
          } else {
            resolve(false)
          }
        }
        reader.readAsArrayBuffer(audioBlob.slice(0, 100))
      })
    }
    
    // 停止录音
    const stopRecording = async () => {
      try {
        // 停止循环录音
        if (recordingInterval) {
          clearInterval(recordingInterval)
          recordingInterval = null
        }
        
        // 停止计时器
        if (durationTimer) {
          clearInterval(durationTimer)
          durationTimer = null
        }
        
        // 停止音频流
        if (audioStream.value) {
          audioStream.value.getTracks().forEach(track => track.stop())
          audioStream.value = null
        }
        
        // 停止音频上下文
        if (audioContext) {
          await audioContext.close()
          audioContext = null
        }
        
        isRecording.value = false
        recordingStartTime.value = null
        recordingDuration.value = 0
        
        // 通知服务器停止录音
        if (websocket.value?.readyState === WebSocket.OPEN) {
          websocket.value.send(JSON.stringify({
            type: 'stop_recording'
          }))
        }
        
        addLog('info', '停止录音')
        
      } catch (error) {
        addLog('error', `停止录音失败: ${error.message}`)
      }
    }
    
    // 音频可视化
    const startAudioVisualization = () => {
      if (!audioStream.value) return
      
      try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)()
        const analyser = audioContext.createAnalyser()
        const source = audioContext.createMediaStreamSource(audioStream.value)
        
        source.connect(analyser)
        analyser.fftSize = 128
        
        const bufferLength = analyser.frequencyBinCount
        const dataArray = new Uint8Array(bufferLength)
        
        const updateVisualization = () => {
          if (!isRecording.value) return
          
          analyser.getByteFrequencyData(dataArray)
          
          // 更新可视化条
          const newBars = []
          for (let i = 0; i < 50; i++) {
            const index = Math.floor(i * bufferLength / 50)
            const height = (dataArray[index] / 255) * 60 + 10
            newBars.push(height)
          }
          
          visualizerBars.value = newBars
          requestAnimationFrame(updateVisualization)
        }
        
        updateVisualization()
      } catch (error) {
        addLog('warning', `音频可视化启动失败: ${error.message}`)
      }
    }
    
    // 录音计时器
    const startRecordingTimer = () => {
      durationTimer = setInterval(() => {
        if (!isRecording.value) {
          clearInterval(durationTimer)
          return
        }
        
        if (recordingStartTime.value) {
          recordingDuration.value = Math.floor((Date.now() - recordingStartTime.value) / 1000)
        }
      }, 1000)
    }
    
    // 添加转录结果
    const addTranscription = (text, timestamp, extraData = {}) => {
      if (!text.trim()) return
      
      transcriptions.value.push({
        text: text.trim(),
        timestamp: timestamp || new Date().toLocaleTimeString(),
        confidence: extraData.confidence || 0,
        processing_time: extraData.processing_time || 0,
        audio_duration: extraData.audio_duration || 0,
        segments: extraData.segments || 0,
        chunk_number: extraData.chunk_number || 0
      })
      
      // 自动滚动到底部
      nextTick(() => {
        if (transcriptionArea.value) {
          transcriptionArea.value.scrollTop = transcriptionArea.value.scrollHeight
        }
      })
    }
    
    // 获取置信度样式类
    const getConfidenceClass = (confidence) => {
      if (confidence > 0.8) return 'high'
      if (confidence > 0.5) return 'medium'
      return 'low'
    }
    
    // 添加日志
    const addLog = (level, message) => {
      logs.value.push({
        level,
        message,
        timestamp: new Date().toLocaleTimeString()
      })
      
      // 限制日志数量
      if (logs.value.length > 100) {
        logs.value = logs.value.slice(-100)
      }
      
      // 自动滚动日志
      nextTick(() => {
        if (logArea.value) {
          logArea.value.scrollTop = logArea.value.scrollHeight
        }
      })
    }
    
    // 清空转录记录
    const clearTranscriptions = () => {
      transcriptions.value = []
      chunkCount.value = 0
      addLog('info', '已清空转录记录')
    }
    
    // 下载转录文本
    const downloadTranscript = () => {
      if (transcriptions.value.length === 0) return
      
      const content = transcriptions.value
        .map(item => {
          const confidence = item.confidence ? ` (置信度: ${(item.confidence * 100).toFixed(0)}%)` : ''
          const time = item.processing_time ? ` [${item.processing_time.toFixed(2)}s]` : ''
          return `[${item.timestamp}] ${item.text}${confidence}${time}`
        })
        .join('\n\n')
      
      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `转录文本_优化版_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      
      addLog('info', '转录文本已下载')
    }
    
    // 获取统计信息
    const getStats = () => {
      if (websocket.value?.readyState === WebSocket.OPEN) {
        websocket.value.send(JSON.stringify({ type: 'get_stats' }))
      }
    }
    
    // 心跳检测
    const startHeartbeat = () => {
      setInterval(() => {
        if (websocket.value?.readyState === WebSocket.OPEN) {
          websocket.value.send(JSON.stringify({ type: 'ping' }))
        }
      }, 30000) // 30秒心跳
    }
    
    // 生命周期
    onMounted(() => {
      addLog('info', '应用已启动（完全优化版）')
      startHeartbeat()
    })
    
    onUnmounted(() => {
      if (isRecording.value) {
        stopRecording()
      }
      if (websocket.value) {
        websocket.value.close()
      }
      if (recordingInterval) {
        clearInterval(recordingInterval)
      }
      if (durationTimer) {
        clearInterval(durationTimer)
      }
      if (audioContext) {
        audioContext.close()
      }
    })
    
    // 返回模板需要的数据和方法
    return {
      // DOM引用
      transcriptionArea,
      logArea,
      
      // 数据
      isConnected,
      isRecording,
      transcriptions,
      logs,
      recordingDuration,
      chunkCount,
      visualizerBars,
      modelInfo,
      performanceStats,
      
      // 计算属性
      connectionStatus,
      connectionStatusText,
      recordingStatusText,
      recordButtonClass,
      recordButtonIcon,
      totalWords,
      successRate,
      avgConfidence,
      avgProcessingTime,
      
      // 方法
      connectWebSocket,
      toggleRecording,
      clearTranscriptions,
      downloadTranscript,
      getStats,
      getConfidenceClass
    }
  }
}
</script>

<style scoped>
/* 基础样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

.container {
  max-width: 1400px;
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border-radius: 20px;
  padding: 30px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
}

.header {
  text-align: center;
  margin-bottom: 40px;
}

.header h1 {
  color: #2c3e50;
  font-size: 2.8em;
  margin-bottom: 10px;
  background: linear-gradient(45deg, #667eea, #764ba2);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header p {
  color: #7f8c8d;
  font-size: 1.2em;
  margin-bottom: 10px;
}

.version-info {
  color: #95a5a6;
  font-size: 0.9em;
}

.version-info span {
  margin: 0 10px;
  padding: 5px 10px;
  background: rgba(149, 165, 166, 0.1);
  border-radius: 15px;
}

.status-bar {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
  background: #f8f9fa;
  padding: 20px;
  border-radius: 15px;
  margin-bottom: 30px;
  border: 2px solid #e9ecef;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.status-dot.connected {
  background: #2ecc71;
  box-shadow: 0 0 10px rgba(46, 204, 113, 0.5);
}

.status-dot.disconnected {
  background: #e74c3c;
}

.status-dot.recording {
  background: #e67e22;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}

.control-panel {
  text-align: center;
  margin-bottom: 40px;
}

.record-button {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: none;
  font-size: 48px;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
  margin: 0 20px;
}

.record-button:before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
  transition: left 0.5s;
}

.record-button:hover:before {
  left: 100%;
}

.record-button.idle {
  background: linear-gradient(45deg, #3498db, #2980b9);
  color: white;
  box-shadow: 0 8px 25px rgba(52, 152, 219, 0.3);
}

.record-button.idle:hover {
  transform: translateY(-5px);
  box-shadow: 0 15px 35px rgba(52, 152, 219, 0.4);
}

.record-button.recording {
  background: linear-gradient(45deg, #e74c3c, #c0392b);
  color: white;
  animation: recordPulse 2s infinite;
}

@keyframes recordPulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}

.action-buttons {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  gap: 15px;
  flex-wrap: wrap;
}

.btn {
  padding: 12px 24px;
  border: none;
  border-radius: 25px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.btn:before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
  transition: left 0.5s;
}

.btn:hover:before {
  left: 100%;
}

.btn-primary {
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
}

.btn-secondary {
  background: linear-gradient(45deg, #95a5a6, #7f8c8d);
  color: white;
}

.btn-info {
  background: linear-gradient(45deg, #3498db, #2980b9);
  color: white;
}

.btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.main-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 30px;
  margin-top: 30px;
}

.panel {
  background: white;
  border-radius: 15px;
  padding: 25px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.panel h3 {
  color: #2c3e50;
  margin-bottom: 20px;
  font-size: 1.4em;
  display: flex;
  align-items: center;
  gap: 10px;
}

.audio-visualizer {
  height: 80px;
  background: linear-gradient(45deg, #f8f9fa, #e9ecef);
  border-radius: 10px;
  margin: 20px 0;
  display: flex;
  align-items: end;
  justify-content: center;
  gap: 2px;
  padding: 10px;
  overflow: hidden;
}

.bar {
  width: 4px;
  background: linear-gradient(to top, #667eea, #764ba2);
  border-radius: 2px;
  transition: height 0.1s ease;
  min-height: 4px;
}

.transcription-area {
  min-height: 300px;
  max-height: 500px;
  overflow-y: auto;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 10px;
  border: 2px dashed #dee2e6;
  font-size: 16px;
  line-height: 1.6;
}

.transcription-item {
  background: white;
  padding: 15px;
  margin-bottom: 15px;
  border-radius: 10px;
  border-left: 4px solid #667eea;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.05);
  animation: slideIn 0.3s ease;
  transition: all 0.3s ease;
}

.transcription-item.high-confidence {
  border-left-color: #2ecc71;
  background: linear-gradient(to right, rgba(46, 204, 113, 0.05), white);
}

.transcription-item.low-confidence {
  border-left-color: #e74c3c;
  background: linear-gradient(to right, rgba(231, 76, 60, 0.05), white);
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}

.timestamp {
  color: #6c757d;
  font-weight: 500;
}

.confidence-badge {
  padding: 3px 8px;
  border-radius: 12px;
  font-weight: bold;
  font-size: 11px;
}

.confidence-badge.high {
  background: #d4edda;
  color: #155724;
}

.confidence-badge.medium {
  background: #fff3cd;
  color: #856404;
}

.confidence-badge.low {
  background: #f8d7da;
  color: #721c24;
}

.processing-time {
  color: #6c757d;
  font-style: italic;
}

.text-content {
  color: #2c3e50;
  font-weight: 500;
  margin: 10px 0;
}

.item-footer {
  display: flex;
  gap: 15px;
  color: #6c757d;
  font-size: 11px;
}

.empty-state {
  text-align: center;
  color: #6c757d;
  font-style: italic;
  padding: 40px 20px;
}

.empty-state .icon {
  font-size: 48px;
  margin-bottom: 15px;
  opacity: 0.5;
}

.optimization-note {
  color: #667eea;
  font-weight: 500;
  margin-top: 10px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
  margin-top: 20px;
}

.stat-card {
  background: linear-gradient(45deg, #667eea, #764ba2);
  color: white;
  padding: 20px;
  border-radius: 12px;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 5px;
}

.stat-label {
  font-size: 14px;
  opacity: 0.9;
}

.log-area {
  min-height: 200px;
  max-height: 400px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  padding: 15px;
  background: #2c3e50;
  color: #ecf0f1;
  border-radius: 8px;
  line-height: 1.5;
}

.log-entry {
  margin-bottom: 8px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  gap: 10px;
}

.log-timestamp {
  color: #3498db;
  min-width: 80px;
}

.log-level {
  min-width: 60px;
  font-weight: bold;
}

.log-level.info { color: #2ecc71; }
.log-level.warning { color: #f39c12; }
.log-level.error { color: #e74c3c; }
.log-level.debug { color: #9b59b6; }

.log-message {
  flex: 1;
}

.performance-panel {
  grid-column: span 2;
  background: linear-gradient(45deg, #f8f9fa, #e9ecef);
  border-radius: 15px;
  padding: 20px;
  margin-top: 30px;
}

.performance-panel h4 {
  color: #2c3e50;
  margin-bottom: 15px;
  font-size: 1.2em;
}

.performance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 15px;
}

.perf-item {
  display: flex;
  justify-content: space-between;
  padding: 10px 15px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.05);
}

.perf-label {
  color: #6c757d;
}

.perf-value {
  font-weight: bold;
  color: #2c3e50;
}

@media (max-width: 768px) {
  .main-content {
    grid-template-columns: 1fr;
  }
  
  .status-bar {
    grid-template-columns: 1fr;
  }
  
  .record-button {
    width: 100px;
    height: 100px;
    font-size: 36px;
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
  
  .performance-panel {
    grid-column: span 1;
  }
  
  .action-buttons {
    flex-direction: column;
    align-items: center;
  }
}
</style>