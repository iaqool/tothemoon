import { GoogleGenerativeAI } from '@google/generative-ai'

function formatMcap(mcap) {
  if (!mcap) return 'Unknown'
  if (mcap >= 1e6) return `$${(mcap / 1e6).toFixed(1)}M`
  if (mcap >= 1e3) return `$${(mcap / 1e3).toFixed(1)}K`
  return `$${mcap}`
}

function sanitizeInput(str) {
  if (typeof str !== 'string') return ''
  return str.replace(/[<>&"'`\\]/g, '').slice(0, 200)
}

function buildFallbackReply(name, ticker, isUpcoming = false, launchpad = '') {
  const tokenRef = ticker ? `${name} ($${ticker})` : name
  
  if (isUpcoming) {
    return `Hi, I saw ${tokenRef} is gearing up for launch${launchpad ? ` on ${launchpad}` : ''} and thought it was the right moment to discuss liquidity and listing support early.

We work with projects ahead of launch to make sure day-one trading does not break on liquidity. TTM gives teams direct access to 2M+ active traders, Top-30 exchange distribution, and clear MM standards from the first trading session.

Our baseline is spread < 1%, daily volume > $10k, and stable depth around the mid price. If your team still needs a lightweight MM setup, we can also support with Listagram.

If your sale timeline is already taking shape, happy to prepare a preliminary listing path before launch.

Best,
The Tothemoon Team
https://tothemoon.agency`
  }

  return `Hi, I've been tracking ${tokenRef}'s recent growth and am really impressed by what your team is building.

We specialize in helping projects like ${tokenRef} maximize visibility across Tier-1/2 CEXs and build sustained liquidity (spread < 1%, volume > $10k). We have a database of 2M+ users and are a Top-30 agency globally.

Also, we provide free tools like Listagram bot for automated listing tracking to help your community stay engaged.

Would love to have a quick 10-min call this week — are you open to it?

Best,
The Tothemoon Team
https://tothemoon.agency`
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  // --- Auth: require API_SECRET ---
  const API_SECRET = process.env.API_SECRET
  if (API_SECRET) {
    const auth = req.headers['authorization']
    if (auth !== `Bearer ${API_SECRET}`) {
      return res.status(401).json({ error: 'Unauthorized' })
    }
  }

  // --- Request size guard ---
  const rawBody = JSON.stringify(req.body || {})
  if (rawBody.length > 4096) {
    return res.status(413).json({ error: 'Payload too large' })
  }

  const { name, chain, mcap, ticker, isUpcoming, launchDate, launchpad } = req.body || {}

  if (!name || !chain) {
    return res.status(400).json({ error: 'Missing project details' })
  }

  const safeName = sanitizeInput(name)
  const safeTicker = sanitizeInput(ticker || '')
  const safeChain = sanitizeInput(chain)
  const safeLaunchpad = sanitizeInput(launchpad || '')

  const fallbackReply = buildFallbackReply(safeName, safeTicker, isUpcoming, safeLaunchpad)
  const apiKey = process.env.GEMINI_API_KEY
  
  if (!apiKey) {
    return res.status(200).json({ reply: fallbackReply })
  }

  try {
    const genAI = new GoogleGenerativeAI(apiKey)
    const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' })

    const toneGuideline = ['Solana', 'TON', 'Base'].includes(safeChain)
      ? 'Use a slightly energetic and informal tone (you can use one emoji like or ). These are often memecoins or hype projects.'
      : 'Use a formal, professional tone. These are typically DeFi or enterprise projects.'

    const launchContext = isUpcoming
      ? `The project is preparing for an upcoming token sale${safeLaunchpad ? ` on ${safeLaunchpad}` : ''}${launchDate ? ` scheduled for ${new Date(launchDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` : ''}. Focus on pre-launch liquidity, day-one trading readiness, and early listing coordination.`
      : 'The project is already live. Focus on current traction, market momentum, and scaling liquidity.'

    const prompt = `You are a professional Business Development Manager at 'Tothemoon', a Top-30 crypto exchange listing agency with 2M+ active traders.

Write exactly ONE engaging, personalized opening sentence for a cold email to the team of a crypto project.

Project Details:
- Name: ${safeName}
- Ticker: ${safeTicker || 'N/A'}
- Blockchain: ${safeChain}
- Market Cap: ${formatMcap(mcap)}
- Context: ${launchContext}

TTM Value Proposition (keep it simple):
- Top-30 exchange globally with 2M+ active users
- Strict liquidity standards: spread < 1%, daily volume > $10k
- Full market making support and exchange distribution
- Free tools like Listagram bot for community engagement

Rules:
1. Start with "Hi," or "Hey," (choose based on tone)
2. Write exactly ONE sentence after the greeting
3. Be natural and conversational, not overly salesy
4. Mention their recent launch, growth, or upcoming sale
5. ${toneGuideline}
6. Do not include subject lines, sign-offs, or any other text
7. Keep it under 30 words

Output example:
Hi, I saw ${safeName}'s recent momentum on ${safeChain} and was really impressed by the trading volume you're building!`

    const result = await model.generateContent(prompt)
    const response = await result.response
    let generatedText = response.text().trim()

    if (generatedText.startsWith('"') && generatedText.endsWith('"')) {
      generatedText = generatedText.slice(1, -1)
    }

    const fullEmail = isUpcoming
      ? `${generatedText}

We work with projects ahead of launch to make sure day-one trading does not break on liquidity. TTM gives teams direct access to 2M+ active traders, Top-30 exchange distribution, and clear MM standards from the first trading session.

Our baseline is spread < 1%, daily volume > $10k, and stable depth around the mid price. If your team still needs a lightweight MM setup, we can also support with Listagram${safeLaunchpad ? ` on ${safeLaunchpad}` : ''}.

If your sale timeline is already taking shape, happy to prepare a preliminary listing path before launch.

Best,
The Tothemoon Team
https://tothemoon.agency`
      : `${generatedText}

We specialize in helping projects like ${safeName} maximize visibility across Tier-1/2 CEXs and build sustained liquidity (spread < 1%, volume > $10k). We have a database of 2M+ users and are a Top-30 agency globally.

Also, we provide free tools like Listagram bot for automated listing tracking to help your community stay engaged.

Would love to have a quick 10-min call this week — are you open to it?

Best,
The Tothemoon Team
https://tothemoon.agency`

    return res.status(200).json({ 
      reply: fullEmail,
      icebreaker: generatedText 
    })
  } catch (error) {
    console.error('Gemini API Error:', error.message)
    return res.status(200).json({ 
      reply: fallbackReply,
      fallback: true 
    })
  }
}
