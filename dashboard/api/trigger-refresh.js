export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' })
  }

  const GITHUB_TOKEN = process.env.GITHUB_TOKEN
  const GITHUB_REPO = process.env.GITHUB_REPO || 'iaqool/tothemoon'

  if (!GITHUB_TOKEN) {
    return res.status(500).json({ error: 'GitHub token not configured' })
  }

  try {
    // Запускаем workflow "Lead Refresh" через GitHub API
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
      const errorText = await response.text()
      console.error('GitHub API Error:', errorText)
      return res.status(response.status).json({ 
        error: 'Failed to trigger workflow',
        details: errorText
      })
    }

    // Получаем последний запуск workflow для отслеживания
    const runsResponse = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/lead-refresh.yml/runs?per_page=1`,
      {
        headers: {
          'Accept': 'application/vnd.github.v3+json',
          'Authorization': `Bearer ${GITHUB_TOKEN}`,
        }
      }
    )

    const runsData = await runsResponse.json()
    const latestRun = runsData.workflow_runs?.[0]

    return res.status(200).json({ 
      success: true,
      message: 'Lead refresh started',
      run_id: latestRun?.id,
      run_url: latestRun?.html_url,
      estimated_time: '5-10 минут'
    })

  } catch (error) {
    console.error('Trigger Error:', error)
    return res.status(500).json({ 
      error: 'Internal server error',
      details: error.message
    })
  }
}
