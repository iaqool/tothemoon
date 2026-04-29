export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  // --- Auth: require API_SECRET ---
  const API_SECRET = process.env.API_SECRET
  if (!API_SECRET) {
    return res.status(500).json({ error: 'API_SECRET not configured' })
  }
  const auth = req.headers['authorization']
  if (auth !== `Bearer ${API_SECRET}`) {
    return res.status(401).json({ error: 'Unauthorized' })
  }

  const GITHUB_TOKEN = process.env.GITHUB_TOKEN
  const GITHUB_REPO = process.env.GITHUB_REPO
  const runId = req.query.run_id

  if (!GITHUB_TOKEN || !GITHUB_REPO) {
    return res.status(500).json({ error: 'Server configuration incomplete' })
  }

  if (!runId) {
    return res.status(400).json({ error: 'run_id is required' })
  }

  // --- Fix SSRF: validate run_id is strictly numeric ---
  if (!/^\d{1,20}$/.test(runId)) {
    return res.status(400).json({ error: 'Invalid run_id format' })
  }

  // --- Validate GITHUB_REPO format ---
  if (!/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(GITHUB_REPO)) {
    return res.status(500).json({ error: 'Invalid repository configuration' })
  }

  try {
    const response = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/runs/${runId}`,
      {
        headers: {
          Accept: 'application/vnd.github.v3+json',
          Authorization: `Bearer ${GITHUB_TOKEN}`,
        },
      }
    )

    if (!response.ok) {
      return res.status(response.status === 404 ? 404 : 502).json({
        error: 'Failed to fetch workflow status',
      })
    }

    const run = await response.json()

    return res.status(200).json({
      success: true,
      run_id: run.id,
      status: run.status,
      conclusion: run.conclusion,
      run_url: run.html_url,
      created_at: run.created_at,
      updated_at: run.updated_at,
      name: run.name,
    })
  } catch (error) {
    console.error('Status Check Error:', error.message)
    return res.status(500).json({ error: 'Internal server error' })
  }
}
