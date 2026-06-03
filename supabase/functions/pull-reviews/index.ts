import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const ALLOWED_EMAIL = 'nguyenhaiquang3@gmail.com'

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, content-type, apikey',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const JSON_HEADERS = { ...CORS, 'Content-Type': 'application/json' }

// ── DataForSEO helpers ────────────────────────────────────────────────────────
function dfsAuth(login: string, password: string) {
  return 'Basic ' + btoa(`${login}:${password}`)
}

async function dfsPost(url: string, payload: unknown, auth: string) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Authorization': auth, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(`DataForSEO ${res.status}`)
  return res.json()
}

async function dfsGet(url: string, auth: string) {
  const res = await fetch(url, { headers: { 'Authorization': auth } })
  if (!res.ok) throw new Error(`DataForSEO GET ${res.status}`)
  return res.json()
}

// ── Main handler ─────────────────────────────────────────────────────────────
// Supports two modes via `action` body field:
//   action = "post"  (default) — post a DataForSEO task, return task_id immediately
//   action = "fetch" — given a task_id, poll once and insert new reviews
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: CORS })

  try {
    // Auth
    const token = req.headers.get('Authorization')?.replace('Bearer ', '') ?? ''
    const db = createClient(Deno.env.get('SUPABASE_URL')!, Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!)
    const { data: { user }, error: authErr } = await db.auth.getUser(token)
    if (authErr || !user || user.email !== ALLOWED_EMAIL) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401, headers: JSON_HEADERS })
    }

    const body = await req.json().catch(() => ({}))
    const action: string = body.action || 'post'

    const dfsLogin = Deno.env.get('DATAFORSEO_LOGIN') || ''
    const dfsPassword = Deno.env.get('DATAFORSEO_PASSWORD') || ''
    if (!dfsLogin || !dfsPassword) {
      return new Response(JSON.stringify({ error: 'DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD secrets not set' }), { status: 500, headers: JSON_HEADERS })
    }
    const auth = dfsAuth(dfsLogin, dfsPassword)
    const base = 'https://api.dataforseo.com/v3'

    // ── Phase 1: Post task, return task_id immediately ────────────────────────
    if (action === 'post') {
      const cid: string = body.cid || Deno.env.get('SALON_CID') || ''
      if (!cid) {
        return new Response(JSON.stringify({ error: 'cid required' }), { status: 400, headers: JSON_HEADERS })
      }

      const postData = await dfsPost(`${base}/business_data/google/reviews/task_post`, [{
        language_name: 'English',
        language_code: 'en',
        location_name: 'United States',
        location_code: 2840,
        cid,
        depth: 100,
        sort_by: 'newest'
      }], auth)

      const taskId = postData?.tasks?.[0]?.id
      if (!taskId) throw new Error('DataForSEO: no task ID returned')

      return new Response(JSON.stringify({ task_id: taskId, cid }), { headers: JSON_HEADERS })
    }

    // ── Phase 2: Fetch task results, insert new reviews ───────────────────────
    if (action === 'fetch') {
      const taskId: string = body.task_id || ''
      const cid: string = body.cid || ''
      const salonNameOverride: string = body.salonName || 'Mi Nail Belleville'

      if (!taskId) {
        return new Response(JSON.stringify({ error: 'task_id required' }), { status: 400, headers: JSON_HEADERS })
      }

      // Poll up to 55 times (55s) for results — 1s interval to fit within edge fn budget
      const getUrl = `${base}/business_data/google/reviews/task_get/${taskId}`
      let reviews: Record<string, unknown>[] = []
      let salonName: string | null = null
      let ready = false

      for (let i = 0; i < 55; i++) {
        await new Promise(r => setTimeout(r, 1000))
        const result = await dfsGet(getUrl, auth)
        const task = result?.tasks?.[0]
        if (!task) continue
        if (task.status_code === 20000) {
          reviews = task.result?.[0]?.items || []
          salonName = task.result?.[0]?.title || null
          ready = true
          break
        }
        if (task.status_code === 40400) break
      }

      if (!ready) {
        return new Response(JSON.stringify({ pending: true, message: 'Task not ready yet, retry in a few seconds' }), { headers: JSON_HEADERS })
      }

      // Insert new reviews
      let newCount = 0
      let skippedCount = 0
      const errors: string[] = []
      const finalSalonName = salonName || salonNameOverride

      for (const review of reviews) {
        const reviewId = (review.id_review || review.review_id) as string
        if (!reviewId) continue

        const { data: existing } = await db
          .from('reviews')
          .select('review_id')
          .eq('review_id', reviewId)
          .maybeSingle()
        if (existing) { skippedCount++; continue }

        const rating = (typeof review.rating === 'object' && review.rating !== null)
          ? ((review.rating as Record<string, unknown>).value as number) || 0
          : (review.rating as number) || 0
        const text = (review.review_text as string) || ''
        const author = (review.profile_name as string) || 'Anonymous'
        const sentimentScore = [5, 9, 8, 6, 4, 2][Math.min(5, Math.max(0, 5 - Math.round(rating)))] ?? 6

        try {
          const { error: insertErr } = await db.from('reviews').insert({
            review_id: reviewId,
            cid,
            salon_name: finalSalonName,
            author_name: author,
            rating,
            original_text: text,
            owner_response: (review.owner_answer as string) || '',
            review_url: (review.review_url as string) || '',
            review_date: (review.timestamp as string) || null,
            profile_image_url: (review.profile_image_url as string) || '',
            author_review_count: (review.reviews_count as number) || 0,
            raw_data: review,
            sentiment_score: sentimentScore,
            risk_flag: false,
            category: 'Other',
            vietnamese_summary: '',
            draft_response: '',
            analysis_json: { source: 'pull-reviews-edge-fn' },
            status: 'ANALYZED'
          })

          if (insertErr) {
            errors.push(`${reviewId}: ${insertErr.message}`)
          } else {
            newCount++
          }
        } catch (e) {
          errors.push(`${reviewId}: ${String(e)}`)
        }
      }

      return new Response(JSON.stringify({
        success: true,
        total_fetched: reviews.length,
        new: newCount,
        skipped: skippedCount,
        errors: errors.length ? errors : undefined
      }), { headers: JSON_HEADERS })
    }

    return new Response(JSON.stringify({ error: 'Unknown action' }), { status: 400, headers: JSON_HEADERS })

  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), { status: 500, headers: JSON_HEADERS })
  }
})
