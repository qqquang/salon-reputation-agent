import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const ALLOWED_EMAIL = 'nguyenhaiquang3@gmail.com'

const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, content-type, apikey',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const JSON_HEADERS = { ...CORS, 'Content-Type': 'application/json' }

// ── Brand context & prompts (mirrors Python pipeline) ────────────────────────
const BRAND_CONTEXT = `Identity: Mi Nail Belleville is a modern neighborhood nail studio focused on clean technique, friendly service, and consistent results.
Tone keywords: playful, warm, caring, polished, confident
Differentiators: detail-oriented shaping and prep, clean and comfortable environment, friendly, no-rush customer care
Core services: gel manicure, acrylic sets, pedicure, nail art
Avoid phrases: We are sorry for any inconvenience, Your satisfaction is our top priority, glowing review, detail-focused care, Mi NAIL`

const SCOUT_PROMPT = (text: string, rating: number) =>
  `You are a salon review triage analyst.
Rating: ${rating}/5
Text: "${text}"

Task:
Classify sentiment, risk, and category for owner operations.

Rules:
- sentiment_score must be an integer 1-10.
- risk_flag is true for high-impact escalation signals, including: legal threats, health/safety or injury claims, discrimination allegations, chargeback/refund threats, extortion, likely fake-review attacks, or explicit intent to damage reputation publicly.
- risk_flag is false for routine dissatisfaction without escalation signals.
- category must be exactly one of: Service Quality, Cleanliness, Price, Staff Attitude, Wait Time, Other.
- If review text is empty or unclear, infer sentiment from rating and keep risk_flag=false, category="Other": rating 5->9, 4->8, 3->6, 2->4, 1->2.

Output format:
Return ONLY valid JSON with exactly these keys:
{"sentiment_score": <int>, "risk_flag": <bool>, "category": "<allowed_value>"}
Do not add markdown. Do not use code fences.`

const TRANSLATE_PROMPT = (text: string, category: string) =>
  `Summarize key points in Vietnamese for the owner.
- Keep it concise (max 25 words).
- Focus on the main praise/complaint and business impact.
- Plain Vietnamese, no emojis.

Category: ${category}
Review: "${text}"`

const DRAFT_PROMPT = (text: string, author: string, salonName: string, sentimentScore: number, recentDrafts: string) => {
  const tone = sentimentScore >= 7 ? 'warm and celebratory' : 'empathetic and calm'
  return `You are the owner of ${salonName}, a neighborhood nail studio. Reply to this Google review as yourself — genuine, casual, and human. Keep it brief (2-3 sentences). Don't use marketing buzzwords or forced nail puns.

Reviewer: ${author}
Rating: ${sentimentScore >= 7 ? '5' : sentimentScore >= 4 ? '3' : '1'}/5
Review: "${text || '(no text — rating only)'}"
Tone: ${tone}
${recentDrafts ? `\nAvoid repeating these recent responses:\n${recentDrafts}` : ''}

Write only the reply text, nothing else.`
}

// ── Anthropic Claude helper ───────────────────────────────────────────────────
async function claudeChat(prompt: string, apiKey: string, model = 'claude-sonnet-4-5'): Promise<string> {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json'
    },
    body: JSON.stringify({
      model,
      max_tokens: 300,
      messages: [{ role: 'user', content: prompt }]
    })
  })
  if (!res.ok) throw new Error(`Anthropic ${res.status}: ${await res.text()}`)
  const data = await res.json()
  return (data.content?.[0]?.text || '').trim()
}

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

async function fetchReviewsFromDFS(cid: string, login: string, password: string, depth = 100): Promise<{ reviews: unknown[], salonName: string | null }> {
  const auth = dfsAuth(login, password)
  const base = 'https://api.dataforseo.com/v3'

  // 1. Post task
  const postData = await dfsPost(`${base}/business_data/google/reviews/task_post`, [{
    language_name: 'English',
    language_code: 'en',
    location_name: 'United States',
    location_code: 2840,
    cid,
    depth,
    sort_by: 'newest'
  }], auth)

  const taskId = postData?.tasks?.[0]?.id
  if (!taskId) throw new Error('DataForSEO: no task ID returned')

  // 2. Poll for results (up to 60s)
  const getUrl = `${base}/business_data/google/reviews/task_get/${taskId}`
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000))
    const result = await dfsGet(getUrl, auth)
    const task = result?.tasks?.[0]
    if (!task) continue
    if (task.status_code === 20000) {
      const items = task.result?.[0]?.items || []
      const title = task.result?.[0]?.title || null
      return { reviews: items, salonName: title }
    }
    if (task.status_code === 40400) break // not found
  }
  return { reviews: [], salonName: null }
}

// ── Main handler ─────────────────────────────────────────────────────────────
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
    const cid: string = body.cid || Deno.env.get('SALON_CID') || ''
    if (!cid) {
      return new Response(JSON.stringify({ error: 'cid required (or set SALON_CID secret)' }), { status: 400, headers: JSON_HEADERS })
    }

    const dfsLogin = Deno.env.get('DATAFORSEO_LOGIN') || ''
    const dfsPassword = Deno.env.get('DATAFORSEO_PASSWORD') || ''

    if (!dfsLogin || !dfsPassword) {
      return new Response(JSON.stringify({ error: 'DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD secrets not set' }), { status: 500, headers: JSON_HEADERS })
    }

    // Fetch reviews from DataForSEO
    const { reviews, salonName } = await fetchReviewsFromDFS(cid, dfsLogin, dfsPassword, 100)

    let newCount = 0
    let skippedCount = 0
    const errors: string[] = []

    for (const review of reviews as Record<string, unknown>[]) {
      const reviewId = (review.id_review || review.review_id) as string
      if (!reviewId) continue

      // Check if already exists
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
      const finalSalonName = salonName || (body.salonName as string) || 'Mi Nail Belleville'

      try {
        // Defaults — used as fallback if Claude calls fail or text is empty
        let sentimentScore = [5, 9, 8, 6, 4, 2][Math.min(5, Math.max(0, 5 - Math.round(rating)))] ?? 6
        let riskFlag = false
        let category = 'Other'
        let vietnameseSummary = ''
        let draftResponse = ''

        // Skip Claude during bulk pull to avoid timeout — use rating-based defaults only.
        // Drafts can be generated on demand via the Regenerate button.

        // Always insert — Claude failures above must not block this
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
          risk_flag: riskFlag,
          category,
          vietnamese_summary: vietnameseSummary,
          draft_response: draftResponse,
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

  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), { status: 500, headers: JSON_HEADERS })
  }
})
