import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const ALLOWED_EMAIL = 'nguyenhaiquang3@gmail.com'

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
      .select('original_text, author_name, salon_name, category, rating, owner_response')
      .eq('review_id', review_id)
      .single()

    if (reviewErr || !review) {
      return new Response(JSON.stringify({ error: 'Review not found' }), { status: 404, headers: corsHeaders })
    }

    if ((review.owner_response || '').trim()) {
      return new Response(JSON.stringify({ error: 'Owner has already replied to this review on Google.' }), { status: 409, headers: corsHeaders })
    }

    // ── Fetch recent drafts for anti-repetition ───────────────────────────────
    const { data: recent } = await db
      .from('review_drafts')
      .select('draft_text')
      .eq('review_id', review_id)
      .order('created_at', { ascending: false })
      .limit(5)

    const context = (recent || []).map((d: { draft_text: string }) => d.draft_text).join('\n---\n')

    // ── Build prompt ──────────────────────────────────────────────────────────
    const prompt = `You are the owner of ${review.salon_name}, a neighborhood nail studio. Reply to this Google review as yourself — genuine, casual, and human. Keep it brief (2-3 sentences). Don't use marketing buzzwords or forced nail puns.

Reviewer: ${review.author_name}
Rating: ${review.rating}/5
Review: "${review.original_text || '(no text — rating only)'}"
${context ? `\nAvoid repeating these recent responses:\n${context}` : ''}

Write only the reply text, nothing else.`

    // ── Call Anthropic Claude ─────────────────────────────────────────────────
    const claudeRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': Deno.env.get('ANTHROPIC_API_KEY') || '',
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-5',
        max_tokens: 300,
        messages: [{ role: 'user', content: prompt }]
      })
    })

    if (!claudeRes.ok) {
      const err = await claudeRes.text()
      return new Response(JSON.stringify({ error: 'Anthropic error', detail: err }), { status: 502, headers: corsHeaders })
    }

    const claudeData = await claudeRes.json()
    const draft_text = claudeData.content?.[0]?.text?.trim()
    if (!draft_text) {
      return new Response(JSON.stringify({ error: 'Empty response from Anthropic' }), { status: 502, headers: corsHeaders })
    }

    // ── Save to review_drafts ─────────────────────────────────────────────────
    const { data: inserted, error: insertErr } = await db
      .from('review_drafts')
      .insert({ review_id, draft_text, is_original: false, model: 'claude-sonnet-4-5' })
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
