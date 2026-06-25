const ALLOWED_ORIGINS = [
  'https://realeyesvr.com',
  'https://www.realeyesvr.com',
];

exports.handler = async function (event) {
  const origin = event.headers.origin || '';
  const allowed = ALLOWED_ORIGINS.includes(origin)
    || origin.includes('localhost')
    || origin.includes('netlify.app');

  const cors = {
    'Access-Control-Allow-Origin':  allowed ? origin : ALLOWED_ORIGINS[0],
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: cors, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers: cors, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  if (!allowed) {
    return { statusCode: 403, headers: cors, body: JSON.stringify({ error: 'Forbidden' }) };
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return {
      statusCode: 500,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Service not configured — contact site admin.' }),
    };
  }

  let payload;
  try {
    payload = JSON.parse(event.body);
  } catch {
    return {
      statusCode: 400,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Invalid request body' }),
    };
  }

  const { image, mediaType, scheduleNotes, weekPhase } = payload;

  if (!image || !scheduleNotes) {
    return {
      statusCode: 400,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: 'Missing image or schedule notes' }),
    };
  }

  const weekCtx = weekPhase ? 'Current project phase/week: ' + weekPhase + '\n' : '';
  const prompt = 'You are a senior construction project manager reviewing a jobsite photo against the project schedule.\n\n'
    + weekCtx
    + 'SCHEDULE NOTES:\n' + scheduleNotes + '\n\n'
    + 'Analyze the uploaded jobsite photo carefully. Provide a structured report with:\n\n'
    + '1. **WHAT I SEE** — Describe visible work-in-place: materials, structural elements, trades working, site conditions. Be specific about locations if identifiable.\n\n'
    + '2. **SCHEDULE COMPARISON** — For each scheduled item, assess:\n'
    + '   - Is it visible / confirmed in the photo?\n'
    + '   - Does it match the expected status (complete, in progress, not started)?\n'
    + '   - Any discrepancy between schedule and what the photo shows?\n\n'
    + '3. **VARIANCES FLAGGED** — List any schedule vs. reality gaps with severity (HIGH / MEDIUM / LOW).\n\n'
    + '4. **SUMMARY** — One paragraph: overall schedule health based on what you can observe, and recommended follow-up actions.\n\n'
    + 'Be direct and use construction industry language. If the photo does not show enough detail to confirm an item, say so explicitly rather than guessing.';

  try {
    const orRes = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + apiKey,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://realeyesvr.com',
        'X-Title': 'RealEyesVR Jobsite Analyzer',
      },
      body: JSON.stringify({
        model: 'qwen/qwen2.5-vl-72b-instruct',
        max_tokens: 1400,
        messages: [{
          role: 'user',
          content: [
            { type: 'image_url', image_url: { url: 'data:' + mediaType + ';base64,' + image } },
            { type: 'text', text: prompt },
          ],
        }],
      }),
    });

    const data = await orRes.json();

    if (!orRes.ok) {
      const msg = (data.error && data.error.message) || ('OpenRouter error ' + orRes.status);
      return {
        statusCode: orRes.status,
        headers: { ...cors, 'Content-Type': 'application/json' },
        body: JSON.stringify({ error: msg }),
      };
    }

    return {
      statusCode: 200,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ result: data.choices[0].message.content }),
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers: { ...cors, 'Content-Type': 'application/json' },
      body: JSON.stringify({ error: err.message || 'Internal server error' }),
    };
  }
};
