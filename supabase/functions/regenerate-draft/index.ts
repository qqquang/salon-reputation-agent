import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const ALLOWED_EMAIL = 'nguyenhaiquang3@gmail.com'

const POLISH_PROMPT = (draft: string) =>
  `You are proofreading a Google review reply for a nail salon.

Check this reply for cringe, cheesy, or overly marketing-speak phrases — especially anything that forces a "nail" pun or sounds like spa ad copy (e.g. "nail fun", "nail game", "nail journey", "pamper", "treat yourself", "indulge", "nail care journey").

Reply text:
"${draft}"

If the reply contains any such phrases, rewrite ONLY the offending sentence(s) to sound natural and human. Return the full corrected reply only.
If the reply is already natural and cringe-free, return exactly: OK`

Deno.serve(async (req) => {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'authorization, content-type, apikey',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
      }
    })
  }

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Content-Type': 'application/json',
  }

  try {
    // ── Auth ──────────────────────────────────────────────────────────────────
    const token = req.headers.get('Authorization')?.replace('Bearer ', '') ?? ''
    const db = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    )
    // Pass token explicitly — this is the correct pattern in Supabase Edge Functions
    const { data: { user }, error: authErr } = await db.auth.getUser(token)
    if (authErr || !user || user.email !== ALLOWED_EMAIL) {
      return new Response(JSON.stringify({ error: 'Unauthorized', detail: authErr?.message }), { status: 401, headers: corsHeaders })
    }

    // ── Parse body ────────────────────────────────────────────────────────────
    const { review_id } = await req.json()
    if (!review_id) {
      return new Response(JSON.stringify({ error: 'review_id required' }), { status: 400, headers: corsHeaders })
    }

    // ── Fetch review ──────────────────────────────────────────────────────────
    const { data: review, error: reviewErr } = await db
      .from('reviews')
      .select('original_text, author_name, salon_name, category')
      .eq('review_id', review_id)
      .single()

    if (reviewErr || !review) {
      return new Response(JSON.stringify({ error: 'Review not found' }), { status: 404, headers: corsHeaders })
    }

    // ── Fetch recent drafts for anti-repetition ───────────────────────────────
    const { data: recent } = await db
      .from('review_drafts')
      .select('draft_text')
      .eq('review_id', review_id)
      .order('created_at', { ascending: false })
      .limit(5)

    const context = (recent || []).map((d: { draft_text: string }) => d.draft_text).join('\n---\n')

    // ── Build prompt (mirrors Python pipeline brand voice) ────────────────────
    const prompt = `Write a public Google review response.
Response language: English only.
Author: ${review.author_name}
Salon: ${review.salon_name}
Review: "${review.original_text}"
Context category: ${review.category || 'General'}
Recent responses to avoid repeating:
${context || 'None'}

Guidelines:
1. Plain text, one paragraph, max 3 sentences, max 350 characters.
2. Voice: Write as a busy owner quickly replying between clients — casual, slightly unpolished, like a real person typing on their phone. Playful and warm. Occasional minor grammar quirks are fine. Avoid spa-marketing vocabulary.
3. Do NOT start with "Thank you" or the author's name.
4. Do NOT use em-dashes (—), bullet points, or formal language.
5. End with a warm invitation to return.
6. Output ONLY the response text, nothing else.
7. Never use these words or phrases: pamper, treat yourself, indulge, glowing review, detail-focused care.`

    // ── Call OpenAI ───────────────────────────────────────────────────────────
    const oaiRes = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${Deno.env.get('OPENAI_API_KEY')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 200,
        temperature: 0.9
      })
    })

    if (!oaiRes.ok) {
      const err = await oaiRes.text()
      return new Response(JSON.stringify({ error: 'OpenAI error', detail: err }), { status: 502, headers: corsHeaders })
    }

    const oaiData = await oaiRes.json()
    let draft_text = (oaiData.choices?.[0]?.message?.content?.trim() || '').replace(/^["']|["']$/g, '')
    if (!draft_text) {
      return new Response(JSON.stringify({ error: 'Empty response from OpenAI' }), { status: 502, headers: corsHeaders })
    }

    // Polish pass: catch cringe phrases GPT slips through
    try {
      const polishedRes = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${Deno.env.get('OPENAI_API_KEY')}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          messages: [{ role: 'user', content: POLISH_PROMPT(draft_text) }],
          max_tokens: 300,
          temperature: 0.3
        })
      })
      const polished = ((await polishedRes.json()).choices?.[0]?.message?.content || '').trim()
      if (polished && polished !== 'OK') {
        draft_text = polished.replace(/^["']|["']$/g, '')
      }
    } catch { /* skip polish on error, keep original */ }

    // ── Save to review_drafts ─────────────────────────────────────────────────
    const { data: inserted, error: insertErr } = await db
      .from('review_drafts')
      .insert({ review_id, draft_text, is_original: false, model: 'gpt-4o-mini' })
      .select('id, draft_text, is_favourite, is_original, created_at')
      .single()

    if (insertErr) {
      return new Response(JSON.stringify({ error: insertErr.message }), { status: 500, headers: corsHeaders })
    }

    return new Response(JSON.stringify(inserted), { headers: corsHeaders })

  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), { status: 500, headers: corsHeaders })
  }
})
