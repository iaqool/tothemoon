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
  const body = JSON.stringify(req.body || {})
  if (body.length > 1024) {
    return res.status(413).json({ error: 'Payload too large' })
  }

  const GITHUB_TOKEN = process.env.GITHUB_TOKEN
  const GITHUB_REPO = process.env.GITHUB_REPO

  if (!GITHUB_TOKEN || !GITHUB_REPO) {
    return res.status(500).json({ error: 'Server configuration incomplete' })
  }

  // --- Validate GITHUB_REPO format ---
  if (!/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+$/.test(GITHUB_REPO)) {
    return res.status(500).json({ error: 'Invalid repository configuration' })
  }

  try {
    const beforeRunsResponse = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/lead-refresh.yml/runs?event=workflow_dispatch&branch=main&per_page=5`,
      {
        headers: {
          'Accept': 'application/vnd.github.v3+json',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
        }
      }
    )

    const beforeRunsData = await beforeRunsResponse.json()
    const knownRunIds = new Set((beforeRunsData.workflow_runs || []).map(run => run.id))

    const response = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/lead-refresh.yml/dispatches`,
      {
        method: 'POST',
        headers: {
          'Accept': 'application/vnd.github.v3+json',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ref: 'main',
          inputs: {
            mode: 'full',
            enrich_limit: '50'
          }
        })
      }
    )

    if (!response.ok) {
      return res.status(502).json({ error: 'Failed to trigger workflow' })
    }

    let latestRun = null
    for (let attempt = 0; attempt < 6; attempt += 1) {
      if (attempt > 0) {
        await new Promise(resolve => setTimeout(resolve, 2000))
      }

      const runsResponse = await fetch(
        `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/lead-refresh.yml/runs?event=workflow_dispatch&branch=main&per_page=10`,
        {
          headers: {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': `Bearer ${GITHUB_TOKEN}`,
          }
        }
      )

      const runsData = await runsResponse.json()
      latestRun = (runsData.workflow_runs || []).find(run => !knownRunIds.has(run.id)) || null

      if (latestRun) {
        break
      }
    }

    return res.status(200).json({ 
      success: true,
      message: 'Lead refresh started',
      run_id: latestRun?.id,
      run_url: latestRun?.html_url,
      estimated_time: '5-10 minutes'
    })

  } catch (error) {
    console.error('Trigger Error:', error.message)
    return res.status(500).json({ error: 'Internal server error' })
  }
}
