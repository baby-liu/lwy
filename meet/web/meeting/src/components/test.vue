<template>
  <div class="test-container">
    <h2>WebSocket连接测试</h2>
    
    <!-- 连接状态 -->
    <div class="status-section">
      <div class="status-item">
        <span class="label">连接状态:</span>
        <span :class="['status', connectionStatus]">{{ connectionText }}</span>
      </div>
      <div class="status-item">
        <span class="label">WebSocket状态:</span>
        <span class="value">{{ websocketState }}</span>
      </div>
    </div>

    <!-- 控制按钮 -->
    <div class="controls">
      <button @click="connect" :disabled="isConnecting || isConnected" class="btn connect">
        {{ isConnecting ? '连接中...' : '连接WebSocket' }}
      </button>
      <button @click="disconnect" :disabled="!isConnected" class="btn disconnect">
        断开连接
      </button>
      <button @click="sendTestMessage" :disabled="!isConnected" class="btn send">
        发送测试消息
      </button>
      <button @click="clearLogs" class="btn clear">
        清空日志
      </button>
    </div>

    <!-- 测试输入 -->
    <div class="input-section">
      <input 
        v-model="testMessage" 
        placeholder="输入测试消息" 
        @keyup.enter="sendCustomMessage"
        :disabled="!isConnected"
        class="message-input"
      >
      <button @click="sendCustomMessage" :disabled="!isConnected" class="btn send">
        发送
      </button>
    </div>

    <!-- 日志区域 -->
    <div class="logs-section">
      <h3>连接日志:</h3>
      <div class="logs" ref="logsContainer">
        <div 
          v-for="(log, index) in logs" 
          :key="index" 
          :class="['log-item', log.type]"
        >
          <span class="timestamp">{{ log.timestamp }}</span>
          <span class="type">{{ log.type.toUpperCase() }}</span>
          <span class="message">{{ log.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onUnmounted, nextTick } from 'vue'

export default {
  name: 'WebSocketTest',
  setup() {
    // 响应式数据
    const websocket = ref(null)
    const isConnected = ref(false)
    const isConnecting = ref(false)
    const logs = ref([])
    const testMessage = ref('Hello WebSocket!')
    const logsContainer = ref(null)

    // 计算属性
    const connectionStatus = computed(() => {
      if (isConnecting.value) return 'connecting'
      return isConnected.value ? 'connected' : 'disconnected'
    })

    const connectionText = computed(() => {
      if (isConnecting.value) return '连接中...'
      return isConnected.value ? '已连接' : '未连接'
    })

    const websocketState = computed(() => {
      if (!websocket.value) return 'NULL'
      switch (websocket.value.readyState) {
        case WebSocket.CONNECTING: return 'CONNECTING (0)'
        case WebSocket.OPEN: return 'OPEN (1)'
        case WebSocket.CLOSING: return 'CLOSING (2)'
        case WebSocket.CLOSED: return 'CLOSED (3)'
        default: return 'UNKNOWN'
      }
    })

    // 添加日志
    const addLog = (type, message) => {
      logs.value.push({
        type,
        message,
        timestamp: new Date().toLocaleTimeString()
      })

      // 限制日志数量
      if (logs.value.length > 50) {
        logs.value = logs.value.slice(-50)
      }

      // 自动滚动到底部
      nextTick(() => {
        if (logsContainer.value) {
          logsContainer.value.scrollTop = logsContainer.value.scrollHeight
        }
      })
    }

    // 连接WebSocket
    const connect = () => {
      if (isConnecting.value || isConnected.value) return

      isConnecting.value = true
      addLog('info', '开始连接WebSocket...')

      try {
        const wsUrl = 'ws://localhost:8000/ws'
        addLog('info', `连接地址: ${wsUrl}`)
        
        websocket.value = new WebSocket(wsUrl)

        // 连接超时处理
        const timeout = setTimeout(() => {
          if (websocket.value && websocket.value.readyState === WebSocket.CONNECTING) {
            addLog('error', 'WebSocket连接超时')
            websocket.value.close()
          }
        }, 10000) // 10秒超时

        websocket.value.onopen = (event) => {
          clearTimeout(timeout)
          isConnecting.value = false
          isConnected.value = true
          addLog('success', 'WebSocket连接成功!')
          addLog('info', `连接事件: ${JSON.stringify({
            type: event.type,
            timeStamp: event.timeStamp
          })}`)
        }

        websocket.value.onmessage = (event) => {
          addLog('receive', `收到消息: ${event.data}`)
          try {
            const data = JSON.parse(event.data)
            addLog('data', `解析后的数据: ${JSON.stringify(data, null, 2)}`)
          } catch (e) {
            addLog('info', '消息不是JSON格式')
          }
        }

        websocket.value.onclose = (event) => {
          clearTimeout(timeout)
          isConnecting.value = false
          isConnected.value = false
          addLog('warning', `WebSocket连接关闭`)
          addLog('info', `关闭详情: code=${event.code}, reason="${event.reason}", wasClean=${event.wasClean}`)
          
          // 解释关闭代码
          const closeReasons = {
            1000: '正常关闭',
            1001: '端点离开',
            1002: '协议错误',
            1003: '不支持的数据类型',
            1006: '异常关闭（通常是网络问题）',
            1011: '服务器错误',
            1015: 'TLS握手失败'
          }
          const reason = closeReasons[event.code] || '未知原因'
          addLog('info', `关闭原因: ${reason}`)
        }

        websocket.value.onerror = (event) => {
          clearTimeout(timeout)
          isConnecting.value = false
          addLog('error', 'WebSocket连接错误')
          addLog('error', `错误事件: ${JSON.stringify({
            type: event.type,
            timeStamp: event.timeStamp
          })}`)
          
          // 提供调试建议
          addLog('info', '调试建议:')
          addLog('info', '1. 检查后端服务是否启动 (python main.py)')
          addLog('info', '2. 访问 http://localhost:8000/health 确认服务正常')
          addLog('info', '3. 检查防火墙是否阻止8000端口')
          addLog('info', '4. 尝试其他端口 (如8001)')
        }

      } catch (error) {
        isConnecting.value = false
        addLog('error', `连接异常: ${error.message}`)
      }
    }

    // 断开连接
    const disconnect = () => {
      if (websocket.value) {
        websocket.value.close(1000, '用户手动断开')
        addLog('info', '主动断开WebSocket连接')
      }
    }

    // 发送测试消息
    const sendTestMessage = () => {
      if (!isConnected.value || !websocket.value) {
        addLog('error', '未连接，无法发送消息')
        return
      }

      const message = JSON.stringify({
        type: 'ping',
        timestamp: new Date().toISOString()
      })

      try {
        websocket.value.send(message)
        addLog('send', `发送测试消息: ${message}`)
      } catch (error) {
        addLog('error', `发送消息失败: ${error.message}`)
      }
    }

    // 发送自定义消息
    const sendCustomMessage = () => {
      if (!isConnected.value || !websocket.value) {
        addLog('error', '未连接，无法发送消息')
        return
      }

      if (!testMessage.value.trim()) {
        addLog('warning', '消息内容为空')
        return
      }

      try {
        websocket.value.send(testMessage.value)
        addLog('send', `发送自定义消息: ${testMessage.value}`)
        testMessage.value = '' // 清空输入框
      } catch (error) {
        addLog('error', `发送消息失败: ${error.message}`)
      }
    }

    // 清空日志
    const clearLogs = () => {
      logs.value = []
      addLog('info', '日志已清空')
    }

    // 组件卸载时清理
    onUnmounted(() => {
      if (websocket.value) {
        websocket.value.close()
      }
    })

    return {
      // 数据
      isConnected,
      isConnecting,
      logs,
      testMessage,
      logsContainer,

      // 计算属性
      connectionStatus,
      connectionText,
      websocketState,

      // 方法
      connect,
      disconnect,
      sendTestMessage,
      sendCustomMessage,
      clearLogs
    }
  }
}
</script>

<style scoped>
.test-container {
  max-width: 800px;
  margin: 20px auto;
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f8f9fa;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

h2 {
  color: #2c3e50;
  text-align: center;
  margin-bottom: 30px;
}

h3 {
  color: #34495e;
  margin: 20px 0 10px 0;
  font-size: 16px;
}

.status-section {
  background: white;
  padding: 15px;
  border-radius: 6px;
  margin-bottom: 20px;
  border: 1px solid #e9ecef;
}

.status-item {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.status-item:last-child {
  margin-bottom: 0;
}

.label {
  font-weight: 600;
  color: #495057;
}

.status {
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.status.connected {
  background: #d4edda;
  color: #155724;
}

.status.disconnected {
  background: #f8d7da;
  color: #721c24;
}

.status.connecting {
  background: #fff3cd;
  color: #856404;
}

.value {
  font-family: monospace;
  font-size: 12px;
  color: #6c757d;
}

.controls {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.input-section {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  align-items: center;
}

.message-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ced4da;
  border-radius: 4px;
  font-size: 14px;
}

.message-input:disabled {
  background: #e9ecef;
  color: #6c757d;
}

.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn.connect {
  background: #28a745;
  color: white;
}

.btn.connect:hover:not(:disabled) {
  background: #218838;
}

.btn.disconnect {
  background: #dc3545;
  color: white;
}

.btn.disconnect:hover:not(:disabled) {
  background: #c82333;
}

.btn.send {
  background: #007bff;
  color: white;
}

.btn.send:hover:not(:disabled) {
  background: #0056b3;
}

.btn.clear {
  background: #6c757d;
  color: white;
}

.btn.clear:hover:not(:disabled) {
  background: #545b62;
}

.logs-section {
  background: white;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid #e9ecef;
}

.logs {
  height: 300px;
  overflow-y: auto;
  padding: 15px;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.4;
  background: #f8f9fa;
}

.log-item {
  display: flex;
  margin-bottom: 4px;
  padding: 2px 0;
}

.timestamp {
  color: #6c757d;
  margin-right: 8px;
  min-width: 70px;
}

.type {
  margin-right: 8px;
  font-weight: bold;
  min-width: 60px;
}

.type.INFO { color: #17a2b8; }
.type.SUCCESS { color: #28a745; }
.type.WARNING { color: #ffc107; }
.type.ERROR { color: #dc3545; }
.type.SEND { color: #6f42c1; }
.type.RECEIVE { color: #fd7e14; }
.type.DATA { color: #20c997; }

.message {
  flex: 1;
  word-break: break-word;
}

/* 滚动条样式 */
.logs::-webkit-scrollbar {
  width: 6px;
}

.logs::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.logs::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.logs::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>