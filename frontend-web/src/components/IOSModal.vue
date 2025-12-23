<script setup lang="ts">
import { X } from 'lucide-vue-next';

// ✅ 关键修改：删除了 import { defineProps... } from 'vue' 这一行
// Vue 3 自动识别 defineProps 和 defineEmits

defineProps({
  isOpen: Boolean,
  title: String,
  fullScreen: Boolean
});

defineEmits(['close']);
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition duration-300 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition duration-200 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="isOpen" class="fixed inset-0 z-50 bg-black/20 backdrop-blur-sm flex items-center justify-center" @click.self="$emit('close')">
        <Transition
          enter-active-class="transition duration-300 cubic-bezier(0.16, 1, 0.3, 1)"
          enter-from-class="transform translate-y-10 opacity-0 scale-95"
          enter-to-class="transform translate-y-0 opacity-100 scale-100"
          leave-active-class="transition duration-200 ease-in"
          leave-from-class="transform translate-y-0 opacity-100 scale-100"
          leave-to-class="transform translate-y-10 opacity-0 scale-95"
        >
          <div class="bg-white/90 backdrop-blur-xl shadow-2xl overflow-hidden flex flex-col" :class="[fullScreen ? 'fixed inset-4 rounded-[2rem]' : 'w-[90%] max-w-lg rounded-3xl max-h-[80vh]']">
            <div class="px-6 py-4 flex justify-between items-center border-b border-gray-100/50">
              <h3 class="font-semibold text-lg text-gray-900 tracking-tight">{{ title }}</h3>
              <button @click="$emit('close')" class="bg-gray-200/50 hover:bg-gray-200 p-1.5 rounded-full transition-colors text-gray-500"><X :size="20" /></button>
            </div>
            <div class="p-6 overflow-y-auto flex-1 text-gray-700"><slot></slot></div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>