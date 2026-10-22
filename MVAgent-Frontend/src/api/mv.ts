/**
 * MV Frontend API — real HTTP calls to the OpenMontage-MV backend.
 *
 * Replaces the mock `generateMagicScript` with an async flow: upload the
 * ASS file → poll for storyboard → load script into editor → monitor for
 * generated shot clips and the final video. All requests go through the
 * Vite proxy (no CORS).
 */

/** 后端返回的分镜脚本（前端 MagicScript 格式） */
export interface MvStoryboard {
  cast: string[]
  characters: Array<{
    id: string
    name: string
    description: string
    style: string
    avatar: string
  }>
  lines: Array<{
    lyrics: string
    lyricsZh: string | null
    scenePrompt: string
    shotPrompt: string
    digitalHumanIds: string[]
    duration: number
    shotNumber: number
  }>
  characterRefs: string[]
}

/** 已生成的视频片段 */
export interface ShotClip {
  shotNumber: number
  videoUrl: string
  coverUrl: string
  duration: number
}

/** 流水线进度 */
export interface PipelineProgress {
  stages: Array<{ name: string; status: string }>
  currentStage: string | null
  finalReady: boolean
}

/** 上传请求（与 mock API 的 MagicScriptRequest 一致） */
export interface UploadRequest {
  songId: string
  assFile: File
  characterImages?: File[]
  extraRequirement?: string
}

const API_BASE = '' // requests go through Vite proxy

/**
 * 上传 ASS 文件，启动 MV 流水线。
 * 后端创建项目目录 + agent session，发消息给 agent 启动流水线。
 */
export async function uploadAss(req: UploadRequest): Promise<{
  sessionId: string
  projectId: string
}> {
  const form = new FormData()
  form.append('songId', req.songId)
  form.append('assFile', req.assFile)
  if (req.characterImages) {
    req.characterImages.forEach((f) => form.append('characterImages', f))
  }
  if (req.extraRequirement) form.append('extraRequirement', req.extraRequirement)

  const res = await fetch(`${API_BASE}/api/mv/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`上传失败 (${res.status}): ${detail}`)
  }
  return res.json()
}

/** 获取 storyboard（前端格式）。未就绪时返回 null。 */
export async function fetchStoryboard(projectId: string): Promise<MvStoryboard | null> {
  const res = await fetch(`${API_BASE}/api/mv/project/${projectId}/storyboard`)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`获取分镜失败 (${res.status})`)
  return res.json()
}

/** 获取已生成的视频片段列表。 */
export async function fetchShots(projectId: string): Promise<ShotClip[]> {
  const res = await fetch(`${API_BASE}/api/mv/project/${projectId}/shots`)
  if (!res.ok) return []
  return res.json()
}

/** 获取流水线进度。 */
export async function fetchProgress(projectId: string): Promise<PipelineProgress> {
  const res = await fetch(`${API_BASE}/api/mv/project/${projectId}/progress`)
  if (!res.ok) throw new Error(`获取进度失败 (${res.status})`)
  return res.json()
}

/**
 * 轮询直到 storyboard 就绪，返回分镜脚本。
 * 每 3 秒轮询一次，超时后抛出错误。
 */
export async function pollStoryboard(
  projectId: string,
  onUpdate?: (progress: PipelineProgress) => void,
  timeoutMs = 300_000, // 5 分钟
): Promise<MvStoryboard> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const progress = await fetchProgress(projectId)
      onUpdate?.(progress)
    } catch {
      // progress 查询失败时静默继续
    }
    const sb = await fetchStoryboard(projectId)
    if (sb) return sb
    await new Promise((r) => setTimeout(r, 3000))
  }
  throw new Error('生成分镜超时（5 分钟），请检查后端 agent 是否正常运行')
}

/**
 * 持续轮询视频片段和最终成片（非阻塞）。
 * 返回 cancel 函数，调用后停止轮询。
 */
export function monitorPipeline(
  projectId: string,
  callbacks: {
    onShotReady?: (shots: ShotClip[]) => void
    onFinalReady?: (videoUrl: string) => void
    onProgress?: (progress: PipelineProgress) => void
  },
  intervalMs = 5000,
): () => void {
  let cancelled = false
  let lastShotCount = 0
  let finalReported = false

  const poll = async () => {
    while (!cancelled) {
      try {
        const progress = await fetchProgress(projectId)
        callbacks.onProgress?.(progress)

        // 检查是否有新的视频片段
        const shots = await fetchShots(projectId)
        if (shots.length > lastShotCount) {
          callbacks.onShotReady?.(shots)
          lastShotCount = shots.length
        }

        // 检查最终成片
        if (progress.finalReady && !finalReported) {
          finalReported = true
          callbacks.onFinalReady?.(`${API_BASE}/media/${projectId}/renders/final.mp4`)
          return // 成片完成，停止轮询
        }

        // 所有阶段完成且无最终视频（storyboard-only 交付）
        if (
          progress.currentStage === 'done' ||
          (progress.stages.length > 0 &&
            progress.stages.every((s) => s.status === 'completed') &&
            !progress.finalReady)
        ) {
          // 流水线完成但没有最终视频（storyboard-only），停止轮询
          if (lastShotCount === 0 && shots.length === 0) return
        }
      } catch {
        // 网络错误时继续轮询
      }
      await new Promise((r) => setTimeout(r, intervalMs))
    }
  }

  poll()

  return () => {
    cancelled = true
  }
}
