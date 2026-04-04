import { useState, useEffect, useCallback } from 'react'
import { supabase } from './lib/supabase'

/* ─── Constants ────────────────────────────────────────────────────────── */
const STATUS_OPTIONS = [
  { value: 'not_contacted', label: 'Не написали' },
  { value: 'contacted', label: 'Написали' },
  { value: 'replied', label: 'Ответили ✅' },
  { value: 'follow_up', label: 'Follow-up ⏰' },
  { value: 'no_response', label: 'Нет ответа' },
]

const STAGE_OPTIONS = [
  { value: 'Stage 1 (Cold)', label: '🧊 Stage 1 — Cold' },
  { value: 'Follow-up 1', label: '⏰ Follow-up 1 (4 дня)' },
  { value: 'Follow-up 2', label: '⏰ Follow-up 2 (10 дней)' },
  { value: 'Stage 2 (Offer)', label: '🔥 Stage 2 — Offer' },
]

const CHAINS = ['Все', 'Solana', 'TON', 'Base', 'Ethereum', 'BNB Chain', 'Tron',
  'Arbitrum', 'Polygon', 'Optimism', 'Injective', 'Stellar', 'Celo']

const PRIORITY_CHAINS = new Set(['Solana', 'TON', 'Base'])
const FOLLOWUP_STAGE_1_DAYS = 4
const FOLLOWUP_STAGE_2_DAYS = 10
const STALE_DAYS = 10
const SENT_TODAY_WINDOW_MS = 24 * 60 * 60 * 1000

function formatLaunchDate(dateStr) {
  if (!dateStr) return 'Upcoming'
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function isUpcomingProject(project) {
  return Boolean(project?.is_upcoming || project?.source === 'ICO Drops')
}

function buildScript(name, ticker, stage = 'Stage 1 (Cold)', contactName = '', options = {}) {
  const hey = contactName ? `Hey ${contactName}!` : 'Hey!'
  const heyAgain = contactName ? `Hey ${contactName},` : 'Hey again!'
  const hi = contactName ? `Hi ${contactName},` : 'Hi!'
  const upcomingContext = options.isUpcoming
    ? `${hey} I saw ${name}${ticker ? ` ($${ticker})` : ''} is preparing for an upcoming token launch${options.launchpad ? ` on ${options.launchpad}` : ''} and thought it made sense to connect before trading goes live.\n\nTTM helps projects secure liquidity from day one with direct access to 2M+ traders, market making requirements aligned for healthy launch conditions, and Listagram if you need a lightweight MM setup.\n\nIf you're planning the launch window now, happy to line up a preliminary listing path early.`
    : null
  const scripts = {
    'Stage 1 (Cold)': upcomingContext || `${hey} I came across ${name} ($${ticker}) and immediately thought it'd be a great fit for our listing services at Tothemoon.\n\nWe specialize in helping projects like yours maximize visibility across Tier-1/2 CEXs and build sustained liquidity (spread < 1%, volume > $10k).\n\nWould love to have a quick 10-min call this week — are you open to it?`,
    'Follow-up 1': `${heyAgain} Just following up on my earlier note about ${name} ($${ticker}).\n\nWe've recently helped similar projects get listed and gain real traction quickly. Happy to share a few case studies if you're curious.\n\nLet me know! 🚀`,
    'Follow-up 2': `${hi} Last note from my side — if the timing isn't right for ${name} ($${ticker}), totally understood.\n\nFeel free to reach out whenever you're ready to explore exchange listing opportunities. Wishing you all the best! 🌙`,
    'Stage 2 (Offer)': `${hey} Great to connect! Here's a quick overview of what Tothemoon offers for ${name} ($${ticker}):\n\n✅ Tier 1-3 CEX listings (including Tier-1 partnerships)\n✅ Market making & deep liquidity (< 1% spread)\n✅ Community & growth campaigns\n✅ Free Listagram bot for automated listing tracking\n\nWould love to set up a detailed call — when works for you?`,
  }
  return scripts[stage] || scripts['Stage 1 (Cold)']
}

function hasIndividualContact(contacts) {
  if (!contacts || contacts.length === 0) return false
  return contacts.some(c => ['BD / Partnerships', 'Founder', 'Listing Manager', 'Growth / Marketing'].includes(c.role))
}

/* ─── Helpers ──────────────────────────────────────────────────────────── */
function formatMcap(val) {
  if (!val || val === 0) return '—'
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`
  if (val >= 1e3) return `$${(val / 1e3).toFixed(1)}K`
  return `$${val.toLocaleString()}`
}

function daysAgo(dateStr) {
  if (!dateStr) return null
  const diff = Date.now() - new Date(dateStr).getTime()
  return Math.floor(diff / (1000 * 60 * 60 * 24))
}

function formatFeedDate(dateStr) {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleString('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function chainClass(chain) {
  const map = { Solana: 'Solana', TON: 'TON', Base: 'Base', Ethereum: 'Ethereum', 'BNB Chain': 'BNB' }
  return `chain-${map[chain] || 'other'}`
}

function chainEmoji(chain) {
  const map = { Solana: '◎', TON: '💎', Base: '🔵', Ethereum: 'Ξ', 'BNB Chain': '🟡',
    Tron: '🔺', Arbitrum: '⚡', Polygon: '🟣', Optimism: '🔴', Injective: '🌊', Celo: '🌿', Stellar: '⭐' }
  return map[chain] || '🔗'
}

function getFollowupThreshold(stage) {
  if (stage === 'Stage 1 (Cold)') return FOLLOWUP_STAGE_1_DAYS
  if (stage === 'Follow-up 1') return FOLLOWUP_STAGE_2_DAYS
  return null
}

function isPendingFollowup(project, latestLog) {
  if (!project || !latestLog) return false
  if (!['contacted', 'follow_up'].includes(project.status)) return false

  const threshold = getFollowupThreshold(latestLog.stage)
  if (threshold === null) return false

  const age = daysAgo(latestLog.sent_at)
  return age !== null && age > threshold
}

function isStaleProject(project, latestLog) {
  if (!project || !latestLog) return false
  if (['replied', 'no_response'].includes(project.status)) return false

  const age = daysAgo(latestLog.sent_at)
  return age !== null && age > STALE_DAYS
}

function getQueueReason(project, projectContacts = [], latestLog) {
  const mcap = Number(project?.mcap || 0)
  const hasEmail = projectContacts.some(contact => contact.platform === 'Email')
  const hasDecisionMaker = projectContacts.some(contact =>
    ['Founder', 'BD / Partnerships', 'Listing Manager', 'Growth / Marketing'].includes(contact.role)
  )

  if (mcap > 1_000_000 && !hasEmail) return 'High MCap - No Email'
  if (!hasEmail && !hasDecisionMaker) return 'No Email / No Decision Maker'
  if (!hasEmail) return 'Email Hunt'
  if (!hasDecisionMaker) return 'No Decision Maker'
  if (isStaleProject(project, latestLog)) return 'Needs Attention'
  return ''
}

function isSentToday(log) {
  if (!log?.sent_at) return false
  return Date.now() - new Date(log.sent_at).getTime() <= SENT_TODAY_WINDOW_MS
}

function getLogStageMeta(stage, projectStatus) {
  if (projectStatus === 'replied') {
    return { label: 'Replied', className: 'badge-replied' }
  }

  if (stage === 'Stage 1 (Cold)') {
    return { label: 'Stage 1', className: 'badge-stage-1' }
  }

  if (stage === 'Follow-up 1' || stage === 'Follow-up 2') {
    return { label: stage, className: 'badge-follow-up' }
  }

  return { label: stage || 'Logged', className: 'badge-stage-default' }
}

function getFeedStatus(projectStatus) {
  if (projectStatus === 'replied') return 'Replied'
  if (projectStatus === 'no_response') return 'Closed'
  return 'Sent'
}

/* ─── CopyScriptBtn ────────────────────────────────────────────────────── */
function CopyScriptBtn({ name, ticker, stage = 'Stage 1 (Cold)', isUpcoming = false, launchpad = '' }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(buildScript(name, ticker, stage, '', { isUpcoming, launchpad }))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button className={`btn-copy ${copied ? 'copied' : ''}`} onClick={handleCopy}>
      {copied ? '✓ Copied' : '📋 Script'}
    </button>
  )
}

/* ─── ContactLinks ─────────────────────────────────────────────────────── */
function ContactLinks({ contacts }) {
  if (!contacts || contacts.length === 0) {
    return <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>—</span>
  }

  return (
    <div className="contact-links">
      {contacts.map(c => {
        const isIndividual = ['BD / Partnerships', 'Founder', 'Listing Manager', 'Growth / Marketing'].includes(c.role)
        const title = c.contact_name
          ? `${c.contact_name} · ${c.role} · ${c.platform}`
          : `${c.role || c.platform} · ${c.value}`

        let icon = null
        if (c.platform === 'Telegram') icon = '✈'
        else if (c.platform === 'X / Twitter') icon = '𝕏'
        else if (c.platform === 'LinkedIn') icon = 'in'
        else if (c.platform === 'Email') icon = '✉'
        else if (c.platform === 'Website') icon = '🌐'
        else if (c.platform === 'CoinGecko') icon = '🦎'
        else if (c.platform === 'ICO Drops') icon = '🔥'
        else if (c.platform === 'Launchpad') icon = '🚀'
        if (!icon) return null

        const href = c.platform === 'Email' ? `mailto:${c.value}` : c.value
        const platformClass = c.platform === 'LinkedIn' ? 'li' : c.platform === 'Email' ? 'email' : ''

        return (
          <a
            key={c.id}
            href={href}
            target="_blank"
            rel="noreferrer"
            className={`contact-link ${c.platform === 'Telegram' ? 'tg' : ''} ${c.platform === 'X / Twitter' ? 'x' : ''} ${platformClass} ${isIndividual ? 'individual' : ''}`}
            title={title}
          >
            {icon}
            {isIndividual && <span className="contact-role-dot" />}
          </a>
        )
      })}
    </div>
  )
}

/* ─── StatusSelect ─────────────────────────────────────────────────────── */
function StatusSelect({ projectId, current, onUpdate }) {
  const handleChange = async (e) => {
    const newStatus = e.target.value
    await supabase.from('projects').update({ status: newStatus }).eq('id', projectId)
    onUpdate(projectId, newStatus)
  }

  return (
    <select className={`status-select status-${current}`} value={current} onChange={handleChange}>
      {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )
}

/* ─── Outreach Log Modal ───────────────────────────────────────────────── */
function OutreachModal({ project, contacts, onClose, onLogged }) {
  const individualContacts = (contacts || []).filter(c =>
    ['BD / Partnerships', 'Founder', 'Listing Manager', 'Growth / Marketing'].includes(c.role)
  )
  const primaryContact = individualContacts[0] || null

  const [stage, setStage] = useState('Stage 1 (Cold)')
  const [selectedContact, setSelectedContact] = useState(primaryContact?.id || '')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)
  const [logs, setLogs] = useState([])
  const [copied, setCopied] = useState(false)
  const [generating, setGenerating] = useState(false)

  const selectedName = (contacts || []).find(c => c.id === selectedContact)?.contact_name || ''

  useEffect(() => {
    setMsg(buildScript(project.name, project.ticker, stage, selectedName, {
      isUpcoming: isUpcomingProject(project),
      launchpad: project.launchpad,
    }))
  }, [stage, project, selectedName])

  useEffect(() => {
    const loadLogs = async () => {
      const contactIds = (contacts || []).map(c => c.id)
      if (contactIds.length === 0) return

      const { data } = await supabase
        .from('outreach_logs')
        .select('*, contacts(platform, value)')
        .in('contact_id', contactIds)
        .order('sent_at', { ascending: false })
        .limit(10)

      setLogs(data || [])
    }

    loadLogs()
  }, [contacts])

  const handleSave = async () => {
    setSaving(true)

    const contact = (contacts || []).find(c => c.id === selectedContact)
      || (contacts || []).find(c => c.platform === 'Telegram' || c.platform === 'X / Twitter')
      || (contacts || [])[0]

    if (!contact) {
      alert('У проекта нет контактов. Сначала добавьте контакт.')
      setSaving(false)
      return
    }

    const { error } = await supabase.from('outreach_logs').insert({
      contact_id: contact.id,
      stage,
      message_sent: msg,
    })

    if (!error) {
      const newStatus = stage === 'Stage 1 (Cold)' ? 'contacted' : 'follow_up'
      await supabase.from('projects').update({ status: newStatus }).eq('id', project.id)
      onLogged(project.id, newStatus)
      onClose()
    }

    setSaving(false)
  }

  const handleCopyMsg = async () => {
    await navigator.clipboard.writeText(msg)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleGenerateReply = async () => {
    setGenerating(true)

    try {
      const res = await fetch('/api/generate-reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: project.name,
          chain: project.chain,
          mcap: project.mcap,
          ticker: project.ticker,
          isUpcoming: isUpcomingProject(project),
          launchDate: project.launch_date,
          launchpad: project.launchpad,
        })
      })

      if (res.ok) {
        const data = await res.json()
        setMsg(data.reply)
      } else {
        alert('Ошибка генерации ответа. Проверьте API ключ в Vercel.')
      }
    } catch (e) {
      console.error(e)
      alert('Ошибка соединения с сервером генерации.')
    }

    setGenerating(false)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">📤 Запись аутрича</div>
            <div className="modal-subtitle">{project.name} ({project.ticker}) · {project.chain}</div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {logs.length > 0 && (
          <div className="log-history">
            <div className="log-history-title">История контактов:</div>
            {logs.map(l => (
              <div key={l.id} className="log-entry">
                <span className="log-stage">{l.stage}</span>
                <span className="log-date">{new Date(l.sent_at).toLocaleDateString('ru-RU')}</span>
                {l.response && <span className="log-response">↳ {l.response}</span>}
              </div>
            ))}
          </div>
        )}

        <div className="modal-form">
          {contacts && contacts.length > 0 && (
            <>
              <label className="form-label">Кому пишем</label>
              <div className="contact-picker">
                {contacts.filter(c => !['Website', 'CoinGecko'].includes(c.platform)).map(c => (
                  <button
                    key={c.id}
                    className={`contact-pill ${selectedContact === c.id ? 'active' : ''}`}
                    onClick={() => setSelectedContact(c.id)}
                  >
                    {c.platform === 'Telegram' ? '✈' : c.platform === 'X / Twitter' ? '𝕏'
                      : c.platform === 'LinkedIn' ? 'in' : c.platform === 'Email' ? '✉' : '👤'}
                    {' '}
                    {c.contact_name ? <strong>{c.contact_name}</strong> : c.value.replace('https://x.com/', '@').replace('https://t.me/', '@')}
                    {c.role && c.role !== 'Team Member' && <span className="pill-role">{c.role}</span>}
                  </button>
                ))}
              </div>
            </>
          )}

          <label className="form-label" style={{ marginTop: '16px' }}>Стадия аутрича</label>
          <select className="filter-select" style={{ width: '100%' }} value={stage} onChange={e => setStage(e.target.value)}>
            {STAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>

          <label className="form-label" style={{ marginTop: '16px', display: 'flex', alignItems: 'center' }}>
            Сообщение
            <button className={`btn-copy ${copied ? 'copied' : ''}`} style={{ marginLeft: '8px' }} onClick={handleCopyMsg}>
              {copied ? '✓ Скопировано' : '📋 Копировать'}
            </button>
            <button
              className="btn-secondary"
              style={{ marginLeft: 'auto', padding: '2px 8px', fontSize: '11px', background: 'var(--accent-purple)', color: 'white', border: 'none' }}
              onClick={handleGenerateReply}
              disabled={generating}
            >
              {generating ? '⏳ Генерация...' : '🤖 Smart Reply'}
            </button>
          </label>
          <textarea className="msg-textarea" value={msg} onChange={e => setMsg(e.target.value)} rows={8} />

          <div className="modal-actions">
            <button className="btn-secondary" onClick={onClose}>Отмена</button>
            <button className="btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? 'Сохранение...' : '✓ Записать отправку'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Feed ─────────────────────────────────────────────────────────────── */
function OutreachFeed({ items, onOpenProject }) {
  return (
    <section className="feed-panel">
      <div className="section-head">
        <div>
          <div className="section-title">Outreach Feed</div>
          <div className="section-subtitle">Последние 20 событий из лога рассылки</div>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="feed-empty">Пока нет записей в outreach_logs</div>
      ) : (
        <div className="feed-list">
          {items.map(item => {
            const stageMeta = getLogStageMeta(item.stage, item.project?.status)

            return (
              <div key={item.id} className="feed-row">
                <button className="feed-project" onClick={() => onOpenProject(item.project)}>
                  {item.project?.name || 'Unknown Project'}
                </button>
                <span className={`feed-badge ${stageMeta.className}`}>{stageMeta.label}</span>
                <span className="feed-channel">{item.channel}</span>
                <span className="feed-date">{formatFeedDate(item.sent_at)}</span>
                <span className="feed-status">{getFeedStatus(item.project?.status)}</span>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

/* ─── SkeletonRow ──────────────────────────────────────────────────────── */
function SkeletonRow() {
  return (
    <tr>{[32, 80, 120, 70, 100, 90, 60, 80].map((w, i) => (
      <td key={i}><div className="skeleton" style={{ height: '16px', width: `${w}px` }} /></td>
    ))}</tr>
  )
}

/* ─── Main App ─────────────────────────────────────────────────────────── */
export default function App() {
  const [projects, setProjects] = useState([])
  const [contacts, setContacts] = useState({})
  const [allLogs, setAllLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterChain, setChain] = useState('Все')
  const [filterStatus, setStatus] = useState('Все')
  const [segment, setSegment] = useState('all')
  const [quickFilters, setQuickFilters] = useState({ priority: false, whales: false, stale: false })
  const [toast, setToast] = useState(null)
  const [modalProject, setModal] = useState(null)

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  const loadData = useCallback(async () => {
    setLoading(true)

    const { data: proj } = await supabase
      .from('projects')
      .select('*')
      .order('created_at', { ascending: false })

    const projList = proj || []
    setProjects(projList)

    if (projList.length === 0) {
      setContacts({})
      setAllLogs([])
      setLoading(false)
      return
    }

    const ids = projList.map(p => p.id)
    const [contactsResult, logsResult] = await Promise.all([
      supabase.from('contacts').select('*').in('project_id', ids),
      supabase
        .from('outreach_logs')
        .select('*, contacts!inner(project_id, platform, value, contact_name)')
        .order('sent_at', { ascending: false })
    ])

    const cont = contactsResult.data || []
    const logsData = logsResult.data || []

    const groupedContacts = {}
    cont.forEach(c => {
      if (!groupedContacts[c.project_id]) groupedContacts[c.project_id] = []
      groupedContacts[c.project_id].push(c)
    })

    const allowedProjectIds = new Set(ids)
    const filteredLogs = logsData.filter(log => allowedProjectIds.has(log.contacts?.project_id))

    setContacts(groupedContacts)
    setAllLogs(filteredLogs)
    setLoading(false)
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleStatusUpdate = (id, newStatus) => {
    setProjects(prev => prev.map(p => p.id === id ? { ...p, status: newStatus } : p))
    showToast(`Статус обновлён → ${STATUS_OPTIONS.find(s => s.value === newStatus)?.label}`)
  }

  const projectById = Object.fromEntries(projects.map(project => [project.id, project]))

  const latestLogByProject = {}
  allLogs.forEach(log => {
    const projectId = log.contacts?.project_id
    if (projectId && !latestLogByProject[projectId]) {
      latestLogByProject[projectId] = log
    }
  })

  const pendingFollowUps = projects.filter(project => isPendingFollowup(project, latestLogByProject[project.id]))
  const staleProjects = projects.filter(project => isStaleProject(project, latestLogByProject[project.id]))
  const upcomingProjects = projects.filter(project => isUpcomingProject(project))
  const sentTodayCount = allLogs.filter(isSentToday).length

  const totalReplied = projects.filter(p => p.status === 'replied').length
  const totalWorked = projects.filter(p => ['contacted', 'follow_up', 'replied'].includes(p.status)).length
  const convRate = totalWorked > 0 ? Math.round((totalReplied / totalWorked) * 100) : 0

  const feedItems = allLogs.slice(0, 20).map(log => ({
    ...log,
    project: projectById[log.contacts?.project_id] || null,
    channel: log.contacts?.platform || 'Unknown',
  }))

  const filtered = projects.filter(project => {
    const q = search.toLowerCase()
    const latestLog = latestLogByProject[project.id]

    const matchSearch = !q || project.name.toLowerCase().includes(q) || (project.ticker || '').toLowerCase().includes(q)
    const matchChain = filterChain === 'Все' || project.chain === filterChain
    const matchStatus = filterStatus === 'Все' || project.status === filterStatus

    let matchSeg = true
    if (segment === 'priority') matchSeg = project.is_priority
    if (segment === 'upcoming') matchSeg = isUpcomingProject(project)
    if (segment === 'medium') matchSeg = !project.is_priority && ['Ethereum', 'BNB Chain', 'Arbitrum', 'Polygon'].includes(project.chain)
    if (segment === 'other') matchSeg = !project.is_priority && !['Ethereum', 'BNB Chain', 'Arbitrum', 'Polygon'].includes(project.chain)
    if (segment === 'followup') matchSeg = pendingFollowUps.some(item => item.id === project.id)

    const matchPriority = !quickFilters.priority || PRIORITY_CHAINS.has(project.chain)
    const matchWhales = !quickFilters.whales || Number(project.mcap || 0) > 1_000_000
    const matchStale = !quickFilters.stale || isStaleProject(project, latestLog)

    return matchSearch && matchChain && matchStatus && matchSeg && matchPriority && matchWhales && matchStale
  })

  const counts = {
    all: projects.length,
    priority: projects.filter(p => p.is_priority).length,
    upcoming: upcomingProjects.length,
    medium: projects.filter(p => !p.is_priority && ['Ethereum', 'BNB Chain', 'Arbitrum', 'Polygon'].includes(p.chain)).length,
    other: projects.filter(p => !p.is_priority && !['Ethereum', 'BNB Chain', 'Arbitrum', 'Polygon'].includes(p.chain)).length,
    followup: pendingFollowUps.length,
  }

  const kpis = [
    { label: 'Total Projects', value: projects.length, tone: 'default' },
    { label: 'Sent Today', value: sentTodayCount, tone: 'blue' },
    { label: 'Pending Follow-ups', value: pendingFollowUps.length, tone: 'orange' },
    { label: 'Conversion Rate', value: `${convRate}%`, tone: 'green' },
  ]

  const quickFilterOptions = [
    { key: 'priority', label: 'Priority' },
    { key: 'whales', label: 'Whales $1M+' },
    { key: 'stale', label: 'Needs Attention' },
  ]

  return (
    <div className="app">
      <header className="header">
        <div className="header-logo">
          <span className="moon-icon">🚀</span>
          <span>Tothemoon</span>
          <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '14px' }}>Lead Gen</span>
        </div>
        <div className="header-stats">
          <div className="stat-pill"><span className="dot" /><span>Live</span></div>
          <div className="stat-pill"><strong>{counts.priority}</strong><span>🔥 Priority</span></div>
          <div className="stat-pill"><strong>{totalReplied}</strong><span>✅ Replies</span></div>
          <div className="stat-pill">
            <strong style={{ color: convRate > 0 ? 'var(--accent-green)' : 'var(--text-primary)' }}>{convRate}%</strong>
            <span>Conv. Rate</span>
          </div>
          {pendingFollowUps.length > 0 && (
            <div className="stat-pill followup-alert">
              <strong>⏰ {pendingFollowUps.length}</strong>
              <span>Follow-ups</span>
            </div>
          )}
          <div className="stat-pill"><strong>{projects.length}</strong><span>Total</span></div>
        </div>
      </header>

      <main className="main-content">
        <section className="kpi-grid">
          {kpis.map(item => (
            <div key={item.label} className={`kpi-card tone-${item.tone}`}>
              <div className="kpi-label">{item.label}</div>
              <div className="kpi-value">{item.value}</div>
            </div>
          ))}
        </section>

        <OutreachFeed
          items={feedItems}
          onOpenProject={(project) => {
            if (project) setModal(project)
          }}
        />

        <div className="segment-tabs">
          {[
            { key: 'all', label: 'All Leads' },
            { key: 'upcoming', label: '🔥 Hot Upcoming', alert: counts.upcoming > 0 },
            { key: 'priority', label: '🔥 Priority' },
            { key: 'medium', label: 'Medium' },
            { key: 'other', label: 'Others' },
            { key: 'followup', label: '⏰ Follow-up', alert: counts.followup > 0 },
          ].map(tab => (
            <button
              key={tab.key}
              className={`seg-tab ${segment === tab.key ? 'active' : ''} ${tab.alert ? 'alert-tab' : ''}`}
              onClick={() => setSegment(tab.key)}
            >
              {tab.label}
              <span className="badge">{counts[tab.key]}</span>
            </button>
          ))}
        </div>

        {segment === 'followup' && pendingFollowUps.length > 0 && (
          <div className="followup-banner">
            ⏰ <strong>{pendingFollowUps.length} проектов</strong> ждут follow-up по правилам 4/10 дней — пора добивать касания.
          </div>
        )}

        <div className="filters-bar">
          <div className="search-box">
            <span className="search-icon">⌕</span>
            <input
              type="text"
              placeholder="Поиск по названию или тикеру..."
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <select className="filter-select" value={filterChain} onChange={e => setChain(e.target.value)}>
            {CHAINS.map(chain => <option key={chain}>{chain}</option>)}
          </select>
          <select className="filter-select" value={filterStatus} onChange={e => setStatus(e.target.value)}>
            <option value="Все">Все статусы</option>
            {STATUS_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <button className="btn-copy" onClick={loadData}>↻ Обновить</button>
        </div>

        <div className="quick-filters">
          {quickFilterOptions.map(filter => (
            <button
              key={filter.key}
              className={`quick-filter ${quickFilters[filter.key] ? 'active' : ''}`}
              onClick={() => setQuickFilters(prev => ({ ...prev, [filter.key]: !prev[filter.key] }))}
            >
              {filter.label}
            </button>
          ))}
          {staleProjects.length > 0 && (
            <div className="quick-filter-meta">Stale сейчас: {staleProjects.length}</div>
          )}
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 32 }}>★</th>
                <th>Проект</th>
                <th>Сеть</th>
                <th>MCap</th>
                <th>Контакты</th>
                <th>Последний контакт</th>
                <th>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? Array(8).fill(0).map((_, i) => <SkeletonRow key={i} />)
                : filtered.length === 0
                  ? (
                    <tr><td colSpan={8}>
                      <div className="empty-state">
                        <div className="icon">🛸</div>
                        <p>{segment === 'followup' ? 'Отлично! Все follow-up актуальны 🎉' : 'Проекты не найдены'}</p>
                      </div>
                    </td></tr>
                    )
                  : filtered.map(project => {
                    const latestLog = latestLogByProject[project.id]
                    const age = latestLog ? daysAgo(latestLog.sent_at) : null
                    const pending = isPendingFollowup(project, latestLog)

                    return (
                      <tr key={project.id} className={pending ? 'row-overdue' : ''}>
                        <td>
                          {project.is_priority && <span className="priority-star" title="Priority">★</span>}
                        </td>
                        <td>
                          <div className="project-name">
                            {project.name}
                            {hasIndividualContact(contacts[project.id]) && (
                              <span className="enriched-badge" title="Найден BD/Founder контакт">🧠</span>
                            )}
                            {isUpcomingProject(project) && <span className="upcoming-dot" title="Upcoming token sale">●</span>}
                          </div>
                          <div className="project-ticker">{project.ticker}</div>
                          {isUpcomingProject(project) && (
                            <div className="launch-date-badge">
                              Launch {formatLaunchDate(project.launch_date)}
                            </div>
                          )}
                          {getQueueReason(project, contacts[project.id] || [], latestLog) && (
                            <div className="queue-reason-badge">{getQueueReason(project, contacts[project.id] || [], latestLog)}</div>
                          )}
                        </td>
                        <td>
                          <span className={`chain-badge ${chainClass(project.chain)}`}>
                            {chainEmoji(project.chain)} {project.chain || '?'}
                          </span>
                        </td>
                        <td>
                          <span className={`mcap-val ${!project.mcap ? 'zero' : ''}`}>
                            {formatMcap(project.mcap)}
                          </span>
                        </td>
                        <td><ContactLinks contacts={contacts[project.id]} /></td>
                        <td>
                          {latestLog
                            ? <div className="last-contact">
                                <div className="last-contact-stage">{latestLog.stage}</div>
                                <div className={`last-contact-days ${pending ? 'overdue' : ''}`}>
                                  {age === 0 ? 'Сегодня' : `${age} дн. назад`}
                                  {pending && ' ⚠️'}
                                </div>
                              </div>
                            : <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Не писали</span>}
                        </td>
                        <td>
                          <StatusSelect projectId={project.id} current={project.status} onUpdate={handleStatusUpdate} />
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '6px' }}>
                            <CopyScriptBtn
                              name={project.name}
                              ticker={project.ticker}
                              stage={latestLog ? (latestLog.stage === 'Stage 1 (Cold)' ? 'Follow-up 1' : 'Follow-up 2') : 'Stage 1 (Cold)'}
                              isUpcoming={isUpcomingProject(project)}
                              launchpad={project.launchpad}
                            />
                            <button className="btn-log" onClick={() => setModal(project)} title="Записать отправку">
                              📤
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: '16px', fontSize: '12px', color: 'var(--text-muted)', textAlign: 'right' }}>
          Показано {filtered.length} из {projects.length} проектов
        </div>
      </main>

      {modalProject && (
        <OutreachModal
          project={modalProject}
          contacts={contacts[modalProject.id]}
          onClose={() => setModal(null)}
          onLogged={(id, status) => {
            handleStatusUpdate(id, status)
            loadData()
          }}
        />
      )}

      {toast && <div className="toast">✓ {toast}</div>}
    </div>
  )
}
