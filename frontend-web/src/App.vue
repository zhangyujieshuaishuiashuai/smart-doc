<script setup lang="ts">
import { ref, nextTick } from 'vue';
import axios from 'axios';
import MarkdownIt from 'markdown-it';
import { Send, Paperclip, FileText, ChevronRight } from 'lucide-vue-next';
import IOSModal from './components/IOSModal.vue';

// ✅ 关键修改 1：显式定义消息接口，解决 isTyping/hasSource 报错
interface Message {
  role: 'user' | 'ai';
  content: string;
  isTyping?: boolean;
  hasSource?: boolean;
  sourceData?: any;
}

// ✅ 关键修改 2：使用泛型 ref<Message[]>
const messages = ref<Message[]>([
  { role: 'ai', content: '你好！我是你的智能文档助手。请上传 PDF 文档，我可以帮你分析其中的文本和表格。' }
]);
const inputVal = ref('');
const isUploading = ref(false);
const showUploadModal = ref(false);
const showSourceModal = ref(false);
const currentSource = ref('');
const fileInput = ref<HTMLInputElement | null>(null);

const md = new MarkdownIt();

// --- API交互 ---
const sendMessage = async () => {
  if (!inputVal.value.trim()) return;

  const userMsg = inputVal.value;
  messages.value.push({ role: 'user', content: userMsg });
  inputVal.value = '';

  // 添加 loading 状态
  messages.value.push({ role: 'ai', content: 'thinking...', isTyping: true });
  scrollToBottom();

  try {
    const res = await axios.post('/api/search', { query: userMsg });

    messages.value.pop(); // 移除 loading
    
    const answer = res.data.context || "未找到相关内容";
    messages.value.push({ 
      role: 'ai', 
      content: answer,
      hasSource: true,
      sourceData: res.data.sources 
    });

  } catch (e) {
    messages.value.pop();
    console.error(e);
    messages.value.push({ role: 'ai', content: '⚠️ 连接后端失败，请检查 Python 程序(8000端口)是否运行。' });
  }
  
  scrollToBottom();
};

const handleUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;
  
  isUploading.value = true;
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await axios.post('/api/upload', formData);
    messages.value.push({ 
      role: 'ai', 
      content: `📄 文档 **${res.data.filename}** 解析完成！\n已存入 ${res.data.chunks_added} 个知识片段（包含表格）。` 
    });
    showUploadModal.value = false;
  } catch (e) {
    console.error(e);
    alert('上传失败');
  } finally {
    isUploading.value = false;
  }
};

const openSource = (msg: Message) => {
  currentSource.value = JSON.stringify(msg.sourceData, null, 2);
  showSourceModal.value = true;
};

const scrollToBottom = () => {
  nextTick(() => {
    const container = document.getElementById('chat-container');
    if (container) container.scrollTop = container.scrollHeight;
  });
};
</script>

<template>
  <div class="h-screen w-screen bg-[#F2F2F7] flex flex-col font-sans overflow-hidden relative">
    <header class="h-16 flex-none bg-white/70 backdrop-blur-md border-b border-gray-200 flex items-center justify-center z-10 sticky top-0">
      <h1 class="text-gray-900 font-semibold text-lg">Smart Doc Assistant</h1>
    </header>

    <main id="chat-container" class="flex-1 overflow-y-auto p-4 space-y-6 scroll-smooth">
      <div v-for="(msg, index) in messages" :key="index" class="flex w-full" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
        <div class="max-w-[80%] px-4 py-3 shadow-sm relative text-[15px] leading-relaxed break-words"
          :class="[msg.role === 'user' ? 'bg-ios-blue text-white rounded-2xl rounded-tr-sm' : 'bg-white text-gray-800 rounded-2xl rounded-tl-sm border border-gray-100']">
          
          <div v-if="msg.isTyping" class="flex space-x-1 h-6 items-center">
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
            <div class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
          </div>
          
          <div v-else v-html="md.render(msg.content)" class="prose prose-sm max-w-none" :class="{'text-white prose-invert': msg.role === 'user'}"></div>
          
          <div v-if="msg.hasSource" class="mt-3 pt-2 border-t border-gray-200/50 flex justify-end">
            <button @click="openSource(msg)" class="text-xs flex items-center text-ios-blue font-medium hover:opacity-70 transition-opacity">
              <FileText :size="14" class="mr-1"/> 查看引用来源 <ChevronRight :size="14"/>
            </button>
          </div>
        </div>
      </div>
    </main>

    <footer class="flex-none bg-white/80 backdrop-blur-xl border-t border-gray-200 p-3 pb-6 safe-area-bottom">
      <div class="max-w-4xl mx-auto flex items-end space-x-3">
        <button @click="showUploadModal = true" class="p-2.5 text-gray-500 hover:bg-gray-100 rounded-full transition-colors flex-none">
          <Paperclip :size="24" />
        </button>
        <div class="flex-1 bg-gray-100 rounded-3xl flex items-center px-4 py-2 border border-transparent focus-within:border-ios-blue/30 focus-within:bg-white transition-all">
          <textarea v-model="inputVal" @keydown.enter.prevent="sendMessage" rows="1" placeholder="输入您的问题..." class="w-full bg-transparent border-none focus:ring-0 text-gray-900 resize-none py-1" style="min-height: 24px; outline: none;"></textarea>
        </div>
        <button @click="sendMessage" class="p-2.5 bg-ios-blue text-white rounded-full shadow-lg hover:bg-blue-600 transition-all flex-none" :disabled="!inputVal.trim()">
          <Send :size="20" />
        </button>
      </div>
    </footer>

    <IOSModal v-if="showUploadModal" :isOpen="showUploadModal" title="上传文档" @close="showUploadModal = false">
      <div class="text-center py-8">
        <div class="border-2 border-dashed border-gray-300 rounded-2xl p-8 hover:border-ios-blue hover:bg-blue-50/50 transition-all cursor-pointer" @click="fileInput?.click()">
          <div class="w-16 h-16 bg-blue-100 text-ios-blue rounded-full flex items-center justify-center mx-auto mb-4"><Paperclip :size="32" /></div>
          <h4 class="text-gray-900 font-medium mb-1">点击选择 PDF 文档</h4>
          <input ref="fileInput" type="file" class="hidden" accept=".pdf" @change="handleUpload">
        </div>
        <p v-if="isUploading" class="mt-4 text-ios-blue font-medium animate-pulse">正在深入分析文档结构 (OCR + 表格)...</p>
      </div>
    </IOSModal>

    <IOSModal v-if="showSourceModal" :isOpen="showSourceModal" title="来源追溯" :fullScreen="true" @close="showSourceModal = false">
      <pre class="bg-gray-50 p-4 rounded-xl overflow-auto h-full font-mono text-xs text-gray-700 border border-gray-200">{{ currentSource }}</pre>
    </IOSModal>
  </div>
</template>

<style>
/* 自定义滚动条 */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: rgba(0, 0, 0, 0.1); border-radius: 10px; }
.safe-area-bottom { padding-bottom: env(safe-area-inset-bottom, 20px); }
</style>