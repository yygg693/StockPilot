<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import LiquidCanvas from '@/components/LiquidCanvas.vue'

const theme = useThemeStore()
theme.initTheme()
</script>

<template>
  <DefaultLayout />
  <LiquidCanvas />
</template>
