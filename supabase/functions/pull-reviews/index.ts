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
Avoid phrases: We are sorry for any inconvenience, Your satisfaction is our top priority, glowing review, detail-focused care, Mi NAIL, pamper, treat yourself, indulge`

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

const POLISH_PROMPT = (draft: string) =>
  `You are proofreading a Google review reply for a nail salon.

Check this reply for cringe, cheesy, or overly marketing-speak phrases — especially anything that forces a "nail" pun or sounds like spa ad copy (e.g. "nail fun", "nail game", "nail journey", "pamper", "treat yourself", "indulge", "nail care journey").

Reply text:
"${draft}"

If the reply contains any such phrases, rewrite ONLY the offending sentence(s) to sound natural and human. Return the full corrected reply only.
If the reply is already natural and cringe-free, return exactly: OK`

const DRAFT_PROMPT = (text: string, author: string, salonName: string, category: string, sentimentScore: number, recentDrafts: string) => {
  const emojiInstruction = sentimentScore < 7 ? 'DO NOT use any emojis.' : 'Use 1-2 appropriate emojis.'
  return `Write a public Google review response.
Response language: English only.
Author: ${author}
Salon: ${salonName}
Review: "${text}"
Context category: ${category}
Recent Responses: ${recentDrafts || 'None.'}

Business context:
${BRAND_CONTEXT}

Guidelines:
1. Keep it natural and human: plain text, one paragraph, max 3 sentences, max 350 characters.
2. Voice: Write as a busy owner quickly replying between clients — casual, slightly unpolished, like a real person typing on their phone. Playful and warm. Occasional minor grammar quirks are fine. Avoid spa-marketing vocabulary.
3. Sound like a real owner: slightly conversational rhythm is good.
4. Safety rules (strict): no personal/private details, no incentives, no asking to remove/edit reviews.
5. If review text is empty, write a simple thank-you only (1-2 short sentences) and do not invent details.
6. Do not imply repeat visits unless the reviewer explicitly says they returned.
7. Do NOT start with "Thank you" or the author's name.
8. ${emojiInstruction}
9. Use the brand name exactly as "Mi Nail Belleville" in the final sentence.
10. End with a warm invitation to return.
11. Output ONLY the response text, nothing else.`
}

// ── OpenAI helper ────────────────────────────────────────────────────────────
async function openAIChat(prompt: string, apiKey: string): Promise<string> {
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 300,
      temperature: 0.7
    })
  })
  if (!res.ok) throw new Error(`OpenAI ${res.status}: ${await res.text()}`)
  const data = await res.json()
  return (data.choices?.[0]?.message?.content || '').trim()
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
    depth
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
    const openaiKey = Deno.env.get('OPENAI_API_KEY') || ''

    if (!dfsLogin || !dfsPassword) {
      return new Response(JSON.stringify({ error: 'DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD secrets not set' }), { status: 500, headers: JSON_HEADERS })
    }
    if (!openaiKey) {
      return new Response(JSON.stringify({ error: 'OPENAI_API_KEY secret not set' }), { status: 500, headers: JSON_HEADERS })
    }

    // Fetch reviews from DataForSEO
    const { reviews, salonName } = await fetchReviewsFromDFS(cid, dfsLogin, dfsPassword, 100)

    // Auto-rename: if Google changed the business name, update all old DB rows for this CID
    if (salonName) {
      const { data: existingRow } = await db
        .from('reviews')
        .select('salon_name')
        .eq('cid', cid)
        .not('salon_name', 'in', '("Unknown Salon","N/A")')
        .limit(1)
        .maybeSingle()
      const existingName = existingRow?.salon_name
      if (existingName && existingName !== salonName) {
        await db
          .from('reviews')
          .update({ salon_name: salonName, updated_at: new Date().toISOString() })
          .eq('cid', cid)
          .neq('salon_name', salonName)
      }
    }

    // Fetch recent drafts for anti-repetition context
    const { data: recentRows } = await db
      .from('reviews')
      .select('draft_response')
      .not('draft_response', 'is', null)
      .order('review_date', { ascending: false })
      .limit(20)
    const recentDrafts = (recentRows || [])
      .map((r: { draft_response: string }) => r.draft_response)
      .filter(Boolean)
      .join('\n- ')

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
        // Scout
        let sentimentScore = [5, 9, 8, 6, 4, 2][Math.min(5, Math.max(0, 5 - Math.round(rating)))] ?? 6
        let riskFlag = false
        let category = 'Other'

        if (text.trim()) {
          const scoutRaw = await openAIChat(SCOUT_PROMPT(text, rating), openaiKey)
          try {
            const scout = JSON.parse(scoutRaw)
            sentimentScore = scout.sentiment_score ?? sentimentScore
            riskFlag = scout.risk_flag ?? false
            category = scout.category ?? 'Other'
          } catch { /* keep defaults */ }
        }

        // Translate
        let vietnameseSummary = ''
        try {
          vietnameseSummary = await openAIChat(TRANSLATE_PROMPT(text, category), openaiKey)
        } catch { /* skip */ }

        // Draft
        let draftResponse = ''
        try {
          draftResponse = await openAIChat(
            DRAFT_PROMPT(text, author, finalSalonName, category, sentimentScore, recentDrafts),
            openaiKey
          )
        } catch { /* skip */ }

        // Polish pass: catch cringe phrases GPT slips through
        if (draftResponse) {
          try {
            const polished = await openAIChat(POLISH_PROMPT(draftResponse), openaiKey)
            if (polished && polished.trim() !== 'OK') {
              draftResponse = polished.trim()
            }
          } catch { /* skip polish on error, keep original */ }
        }

        // Insert
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
