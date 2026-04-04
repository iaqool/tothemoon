import { GoogleGenerativeAI } from '@google/generative-ai'

function formatMcap(mcap) {
  if (!mcap) return 'Unknown'
  if (mcap >= 1e9) return `$${(mcap / 1e9).toFixed(2)}B`
  if (mcap >= 1e6) return `$${(mcap / 1e6).toFixed(2)}M`
  if (mcap >= 1e3) return `$${(mcap / 1e3).toFixed(1)}K`
  return `$${mcap}`
}

function getTone(chain) {
  return ['Solana', 'TON', 'Base'].includes(chain) ? 'energetic' : 'formal'
}

function buildFallbackReply(name, ticker, chain, isUpcoming = false, launchpad = '') {
  const tokenRef = ticker ? `${name} (${ticker})` : name
  if (isUpcoming) {
    return `Thanks for sharing the upcoming launch plans for ${tokenRef}${launchpad ? ` on ${launchpad}` : ''}. TTM is a Top-30 global exchange with 2M+ active users across 160+ countries, 300+ listed assets, and a CER 3-star security rating, and we help teams secure launch-day liquidity from the start. Our market making baseline is an average spread below 1%, daily trading volume above $10,000, and at least $1,000 depth within +/-1.9% of the mid price; if needed, we can also support with Listagram as a lightweight liquidity tool. Please share your token ticker, chain or contract standard, preferred launch timeline, and best TG or email contact so we can prepare a preliminary listing offer.`
  }
  const intro = ['Solana', 'TON', 'Base'].includes(chain)
    ? `Hey! Love the momentum ${tokenRef} is building on ${chain}.`
    : `Thanks for your interest in listing ${tokenRef} on Tothemoon.`

  return `${intro} TTM is a Top-30 global exchange with 2M+ active users across 160+ countries, 300+ listed assets, and a CER 3-star security rating. For listing readiness, we require an average spread below 1%, daily trading volume above $10,000, and at least $1,000 depth within +/-1.9% of the mid price. If your team does not yet have a market maker, we can also offer Listagram as a free liquidity support tool. Please share your token ticker, chain/contract standard, preferred listing timeline, and best TG or email contact so we can prepare a preliminary offer.`
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const { name, chain, mcap, ticker, isUpcoming, launchDate, launchpad } = req.body || {}

  if (!name || !chain) {
    return res.status(400).json({ error: 'Missing project details' })
  }

  const fallbackReply = buildFallbackReply(name, ticker, chain, isUpcoming, launchpad)
  const apiKey = process.env.GEMINI_API_KEY
  if (!apiKey) {
    return res.status(200).json({ reply: fallbackReply })
  }

  try {
    const genAI = new GoogleGenerativeAI(apiKey)
    const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' })
    const tone = getTone(chain)

    const upcomingContext = isUpcoming
      ? `This project is still pre-launch${launchpad ? ` and is preparing for a sale on ${launchpad}` : ''}${launchDate ? ` with a target launch date around ${launchDate}` : ''}. Angle the reply around launch-day liquidity, pre-listing coordination, and getting the project in front of traders before momentum peaks.`
      : 'This project is already live or actively trading. Angle the reply around listing readiness and current liquidity conditions.'

    const prompt = `You are the lead listing manager at Tothemoon (TTM). Write one short outbound-ready reply in English for a crypto project asking about listing or market making requirements.

Project context:
- Project name: ${name}
- Ticker: ${ticker || 'Unknown'}
- Chain: ${chain}
- Market cap: ${formatMcap(mcap)}
- Launchpad: ${launchpad || 'Unknown'}
- Upcoming project: ${isUpcoming ? 'Yes' : 'No'}

Strategic context:
- ${upcomingContext}

Required facts to include naturally:
- TTM is a Top-30 global exchange.
- TTM has 2M+ active users across 160+ countries.
- TTM has 300+ listed assets and a CER 3-star security rating.
- Market making requirements: average spread below 1% over 24 hours, daily volume above $10,000, and at least $1,000 order book depth within +/-1.9% from the mid price.
- Mention full marketing support such as AMA sessions, airdrops, and trading competitions.
- If the project may not have a market maker yet, mention Listagram as a free liquidity support tool.

Tone rules:
- Overall tone for this project: ${tone}.
- If chain is Solana, TON, or Base, use an energetic tone and you may use one fitting emoji.
- Otherwise use a formal, confident, professional tone.
- Keep it concise: 4 to 6 sentences.
- No bullet points.
- No fluff.

The reply must end with a CTA asking for these details so you can prepare a preliminary listing offer:
- token name or ticker
- blockchain / contract standard
- preferred listing timeline
- best TG or email contact

Return only the final reply text.`

    const result = await model.generateContent(prompt)
    const text = result.response.text()?.trim()

    return res.status(200).json({ reply: text || fallbackReply })
  } catch (error) {
    console.error('Gemini API Error:', error)
    return res.status(200).json({ reply: fallbackReply })
  }
}
