<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { apiGet } from '../api'
import { enqueueNeteaseTracks, summarizeBulkEnqueueFailures } from '../utils/queue'
import { getFavoritePlaylists, toggleFavoritePlaylist } from '../utils/favorites'
import { 
  ListMusic, 
  RefreshCw, 
  AlertCircle,
  Music,
  User,
  Calendar,
  Play,
  Plus,
  Heart,
  TrendingUp,
  Star,
  Search,
  X,
  Loader2
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const router = useRouter()
const error = ref('')
const status = ref('')
const loading = ref(false)
const categories = ref<any[]>([])
const selectedCategory = ref('全部')
const playlists = ref<any[]>([])
const highQualityPlaylists = ref<any[]>([])
const recommendPlaylists = ref<any[]>([])
const searchKeywords = ref('')
const searchResults = ref<any[]>([])
const searchLoading = ref(false)
const searchPage = ref(1)
const searchHasMore = ref(false)
const isSearchMode = computed(() => Boolean(searchKeywords.value.trim()))

const scrollEl = ref<HTMLElement | null>(null)
const STATE_KEY = 'tsbot:state:/playlists'

const favoritePlaylistIds = ref<Set<number>>(new Set())

function refreshFavoritePlaylistIds() {
  favoritePlaylistIds.value = new Set(getFavoritePlaylists().map((p) => Number(p.id)))
}

function isLocalFavPlaylist(id: number | string): boolean {
  const n = Number(id)
  if (!Number.isFinite(n) || n <= 0) return false
  return favoritePlaylistIds.value.has(n)
}

function toggleLocalFavPlaylist(pl: any) {
  toggleFavoritePlaylist(pl)
  refreshFavoritePlaylistIds()
}

async function loadCategories() {
  try {
    const res = await apiGet<any>('/netease/playlist/categories')
    categories.value = res?.sub || []
  } catch (e) {
    console.error('Failed to load categories:', e)
  }
}

async function loadPlaylists(cat: string = '全部') {
  loading.value = true
  error.value = ''
  
  try {
    const [topRes, highQualityRes, recommendRes] = await Promise.all([
      apiGet<any>(`/netease/playlist/top?cat=${encodeURIComponent(cat)}&limit=30`),
      apiGet<any>(`/netease/playlist/highquality?cat=${encodeURIComponent(cat)}&limit=10`),
      apiGet<any>('/netease/recommend/playlists?limit=10')
    ])
    
    playlists.value = topRes?.playlists || []
    highQualityPlaylists.value = highQualityRes?.playlists || []
    recommendPlaylists.value = recommendRes?.result || []
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  } finally {
    loading.value = false
  }
}

async function selectCategory(cat: string) {
  selectedCategory.value = cat
  await loadPlaylists(cat)
}

async function searchPlaylists(loadMore = false) {
  const keywords = searchKeywords.value.trim()
  if (!keywords) {
    searchResults.value = []
    searchHasMore.value = false
    return
  }

  searchLoading.value = true
  error.value = ''
  if (!loadMore) {
    searchPage.value = 1
    searchResults.value = []
  } else {
    searchPage.value += 1
  }

  try {
    const limit = 24
    const offset = (searchPage.value - 1) * limit
    const res = await apiGet<{ playlists: any[]; total: number }>(
      `/netease/search/playlists?keywords=${encodeURIComponent(keywords)}&limit=${limit}&offset=${offset}`,
    )
    const items = (res?.playlists || []).map((playlist: any) => ({
      id: playlist.id,
      name: playlist.name,
      coverImgUrl: playlist.cover_img_url,
      playCount: Number(playlist.play_count) || 0,
      trackCount: Number(playlist.track_count) || 0,
      creator: { nickname: playlist.creator || '未知创建者' },
    }))
    searchResults.value = loadMore ? [...searchResults.value, ...items] : items
    searchHasMore.value =
      searchResults.value.length < Number(res?.total || 0) && items.length === limit
  } catch (e: any) {
    if (loadMore) searchPage.value -= 1
    error.value = String(e?.message ?? e)
  } finally {
    searchLoading.value = false
  }
}

function clearSearch() {
  searchKeywords.value = ''
  searchResults.value = []
  searchHasMore.value = false
  searchPage.value = 1
  error.value = ''
  if (!playlists.value.length) void loadPlaylists(selectedCategory.value)
}

function goToPlaylist(id: number | string) {
  saveState()
  router.push(`/playlist/${id}`)
}

function saveState() {
  const el = scrollEl.value
  if (!el) return
  sessionStorage.setItem(
    STATE_KEY,
    JSON.stringify({
      category: selectedCategory.value,
      query: searchKeywords.value,
      scrollTop: el.scrollTop || 0,
    }),
  )
}

function loadSavedState(): { category?: string; query?: string; scrollTop?: number } {
  try {
    const raw = sessionStorage.getItem(STATE_KEY)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return typeof obj === 'object' && obj ? obj : {}
  } catch {
    return {}
  }
}

async function restoreScroll(top: number) {
  const el = scrollEl.value
  if (!el) return
  if (!Number.isFinite(top) || top <= 0) return
  await nextTick()
  el.scrollTop = top
}

onBeforeRouteLeave(() => {
  saveState()
  return true
})

async function addPlaylistToQueue(playlist: any) {
  error.value = ''
  status.value = ''
  
  try {
    const detailRes = await apiGet<any>(`/netease/playlist/${playlist.id}/detail`)
    const tracks = detailRes?.playlist?.tracks || []
    
    if (tracks.length === 0) {
      error.value = '歌单为空或无法获取歌曲'
      return
    }

    const confirmed = confirm(
      `确定要将歌单《${playlist.name}》的全部 ${tracks.length} 首歌曲添加到播放队列吗？

歌单较大时可能需要一点时间，请耐心等待。`,
    )
    
    if (!confirmed) {
      return
    }

    const result = await enqueueNeteaseTracks(tracks, {
      onProgress(current, total, title) {
        status.value = `正在添加 ${current}/${total}：${title}`
      },
    })

    if (result.failed.length > 0) {
      error.value = `有 ${result.failed.length} 首歌曲添加失败：${summarizeBulkEnqueueFailures(result.failed)}`
    }

    status.value = result.failed.length > 0
      ? `已添加 ${result.addedCount} 首歌曲到播放队列，${result.failed.length} 首失败`
      : `已添加 ${result.addedCount} 首歌曲到播放队列`
    setTimeout(() => {
      status.value = ''
    }, 5000)
  } catch (e: any) {
    error.value = String(e?.message ?? e)
  }
}

function formatPlayCount(count: number): string {
  if (count >= 100000000) {
    return `${(count / 100000000).toFixed(1)}亿`
  } else if (count >= 10000) {
    return `${(count / 10000).toFixed(1)}万`
  }
  return count.toString()
}

onMounted(() => {
  void (async () => {
    const saved = loadSavedState()
    const savedCategory = typeof saved.category === 'string' && saved.category ? saved.category : '全部'
    selectedCategory.value = savedCategory
    searchKeywords.value = typeof saved.query === 'string' ? saved.query : ''

    refreshFavoritePlaylistIds()
    await loadCategories()
    if (searchKeywords.value.trim()) {
      await searchPlaylists()
    } else {
      await loadPlaylists(selectedCategory.value)
    }
    await restoreScroll(Number(saved.scrollTop ?? 0))
  })()
})
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50">
    <!-- Header -->
    <div class="bg-white/80 backdrop-blur-md border-b border-gray-200 px-6 py-4 sticky top-0 z-20 shadow-sm transition-all duration-300">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <ListMusic :size="28" class="text-blue-600" />
          发现歌单
        </h1>
        <button 
          @click="loadPlaylists(selectedCategory)"
          :disabled="loading"
          class="btn-secondary text-sm py-1.5 px-3"
        >
          <RefreshCw :size="16" :class="{ 'animate-spin': loading }" />
          <span class="hidden sm:inline">刷新</span>
        </button>
      </div>

      <form class="relative mb-4 max-w-2xl" @submit.prevent="searchPlaylists()">
        <Search :size="18" class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          v-model="searchKeywords"
          type="search"
          placeholder="搜索歌单名称或创建者..."
          class="w-full rounded-xl border border-gray-200 bg-gray-50 py-2.5 pl-10 pr-24 text-sm text-gray-900 outline-none transition-colors placeholder:text-gray-400 focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-100"
        />
        <button
          v-if="searchKeywords"
          type="button"
          class="absolute right-16 top-1/2 -translate-y-1/2 rounded-md p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-label="清除歌单搜索"
          @click="clearSearch"
        >
          <X :size="16" />
        </button>
        <button
          type="submit"
          :disabled="searchLoading || !searchKeywords.trim()"
          class="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Loader2 v-if="searchLoading" :size="16" class="animate-spin" />
          <span v-else>搜索</span>
        </button>
      </form>

      <!-- Category filter -->
      <div v-if="!isSearchMode && categories.length > 0" class="flex flex-wrap gap-2">
        <button
          @click="selectCategory('全部')"
          class="px-4 py-1.5 text-sm rounded-full transition-all duration-200 font-medium border"
          :class="[
            selectedCategory === '全部' 
              ? 'bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-200' 
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
          ]"
        >
          全部
        </button>
        <button
          v-for="category in categories.slice(0, 15)"
          :key="category.name"
          @click="selectCategory(category.name)"
          class="px-4 py-1.5 text-sm rounded-full transition-all duration-200 font-medium border"
          :class="[
            selectedCategory === category.name 
              ? 'bg-blue-600 text-white border-blue-600 shadow-md shadow-blue-200' 
              : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 hover:border-gray-300'
          ]"
        >
          {{ category.name }}
        </button>
      </div>
    </div>

    <!-- Content -->
    <div ref="scrollEl" class="flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-6 pb-24 scrollbar-thin">
      <!-- Status messages -->
      <div v-if="error" class="mb-6 bg-red-50 border border-red-200 rounded-xl p-4 flex items-center gap-3 text-red-700">
        <AlertCircle :size="20" class="flex-shrink-0" />
        <div>
          <div class="font-medium">加载失败</div>
          <div class="text-sm opacity-90">{{ error }}</div>
        </div>
      </div>
      
      <div v-if="status" class="mb-6 bg-green-50 border border-green-200 rounded-xl p-4 flex items-center gap-3 text-green-700 status-success shadow-sm">
        <div class="font-medium">{{ status }}</div>
      </div>
      
      <!-- Loading state -->
      <div v-if="(loading && !playlists.length) || (searchLoading && !searchResults.length)" class="h-64 flex items-center justify-center">
        <LoadingSpinner text="正在加载歌单..." />
      </div>
      
      <!-- Content sections -->
      <div v-else class="space-y-10 max-w-[1600px] mx-auto">
        <section v-if="isSearchMode" class="fade-in">
          <div class="mb-5 flex items-center justify-between">
            <h2 class="flex items-center gap-2 text-xl font-bold text-gray-900">
              <Search :size="22" class="text-blue-600" />
              “{{ searchKeywords.trim() }}”的搜索结果
            </h2>
            <span class="text-sm text-gray-500">{{ searchResults.length }} 个歌单</span>
          </div>

          <div v-if="searchResults.length" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in searchResults"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, name: playlist.name, coverImgUrl: playlist.coverImgUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img
                  :src="playlist.coverImgUrl + '?param=300y300'"
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                  <div
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }} · {{ playlist.trackCount }} 首
                </p>
              </div>
            </div>
          </div>

          <EmptyState
            v-else-if="!searchLoading"
            :icon="Search"
            title="没有找到相关歌单"
            description="换个歌单名称或创建者试试"
          />

          <div v-if="searchHasMore" class="mt-8 flex justify-center">
            <button class="btn-secondary px-6" :disabled="searchLoading" @click="searchPlaylists(true)">
              <Loader2 v-if="searchLoading" :size="16" class="animate-spin" />
              <span v-else>加载更多</span>
            </button>
          </div>
        </section>

        <!-- High quality playlists -->
        <section v-if="!isSearchMode && highQualityPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <Star :size="24" class="text-yellow-500 fill-yellow-500" />
            精品歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in highQualityPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, name: playlist.name, coverImgUrl: playlist.coverImgUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <!-- Play Count Badge -->
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Recommended playlists -->
        <section v-if="!isSearchMode && recommendPlaylists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <TrendingUp :size="24" class="text-green-500" />
            推荐歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in recommendPlaylists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, name: playlist.name, picUrl: playlist.picUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.picUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-green-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-green-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
              </div>
            </div>
          </div>
        </section>

        <!-- All playlists -->
        <section v-if="!isSearchMode && playlists.length > 0" class="fade-in">
          <h2 class="text-xl font-bold text-gray-900 mb-5 flex items-center gap-2">
            <ListMusic :size="24" class="text-blue-500" />
            {{ selectedCategory }} 歌单
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4 md:gap-6">
            <div
              v-for="playlist in playlists"
              :key="playlist.id"
              class="group relative flex flex-col gap-3 cursor-pointer"
              @click="goToPlaylist(playlist.id)"
            >
              <div class="relative aspect-square rounded-xl overflow-hidden shadow-sm transition-all duration-300 group-hover:shadow-xl group-hover:-translate-y-1">
                <button
                  class="absolute top-2 left-2 z-10 p-1.5 rounded-full backdrop-blur-md transition-colors"
                  :class="isLocalFavPlaylist(playlist.id) ? 'bg-pink-50 text-pink-600' : 'bg-black/40 text-white/90 hover:bg-pink-50 hover:text-pink-600'"
                  @click.stop="toggleLocalFavPlaylist({ id: playlist.id, name: playlist.name, coverImgUrl: playlist.coverImgUrl, playCount: playlist.playCount, creator: playlist.creator })"
                  :title="isLocalFavPlaylist(playlist.id) ? '取消本地收藏' : '本地收藏'"
                >
                  <Heart :size="14" :fill="isLocalFavPlaylist(playlist.id) ? 'currentColor' : 'none'" />
                </button>
                <img 
                  :src="playlist.coverImgUrl + '?param=300y300'" 
                  :alt="playlist.name"
                  class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                />
                 <!-- Hover Overlay -->
                <div class="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-[2px]">
                   <div 
                    class="w-12 h-12 bg-white/90 rounded-full flex items-center justify-center text-blue-600 shadow-lg transform scale-50 group-hover:scale-100 transition-transform duration-300 hover:bg-white hover:scale-110"
                    @click.stop="addPlaylistToQueue(playlist)"
                    title="添加到播放队列"
                  >
                    <Play :size="24" fill="currentColor" class="ml-1" />
                  </div>
                </div>
                <div class="absolute top-2 right-2 bg-black/60 backdrop-blur-md text-white text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Play :size="10" fill="currentColor" />
                  {{ formatPlayCount(playlist.playCount) }}
                </div>
              </div>
              
              <div class="min-w-0">
                <h3 class="font-bold text-gray-900 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors mb-1" :title="playlist.name">
                  {{ playlist.name }}
                </h3>
                <p class="text-xs text-gray-500 flex items-center gap-1 truncate">
                  <User :size="12" />
                  {{ playlist.creator?.nickname }}
                </p>
              </div>
            </div>
          </div>
        </section>

        <!-- Empty state -->
        <EmptyState
          v-if="!isSearchMode && !loading && playlists.length === 0 && highQualityPlaylists.length === 0 && recommendPlaylists.length === 0"
          :icon="ListMusic"
          title="暂无歌单"
          description="尝试选择其他分类或刷新页面"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
