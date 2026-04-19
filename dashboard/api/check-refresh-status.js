export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const GITHUB_TOKEN = process.env.GITHUB_TOKEN
  const GITHUB_REPO = process.env.GITHUB_REPO || 'iaqool/tothemoon'
  const runId = req.query.run_id

  if (!GITHUB_TOKEN) {
    return res.status(500).json({ error: 'GitHub token not configured' })
  }

  if (!runId) {
    return res.status(400).json({ error: 'run_id is required' })
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
      const errorText = await response.text()
      console.error('GitHub Status API Error:', errorText)
      return res.status(response.status).json({
        error: 'Failed to fetch workflow status',
        details: errorText,
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
    console.error('Status Check Error:', error)
    return res.status(500).json({
      error: 'Internal server error',
      details: error.message,
    })
  }
}
