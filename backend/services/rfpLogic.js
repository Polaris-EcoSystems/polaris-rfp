function parseUsDate(dateStr) {
  if (!dateStr || typeof dateStr !== 'string') return null
  const s = dateStr.trim()
  if (!s || s.toLowerCase() === 'not available') return null
  const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (!m) return null
  const mm = parseInt(m[1], 10)
  const dd = parseInt(m[2], 10)
  const yyyy = parseInt(m[3], 10)
  if (!mm || !dd || !yyyy) return null
  const d = new Date(yyyy, mm - 1, dd)
  if (Number.isNaN(d.getTime())) return null
  if (d.getFullYear() !== yyyy || d.getMonth() !== mm - 1 || d.getDate() !== dd)
    return null
  return d
}

function daysUntil(d, now = new Date()) {
  if (!d) return null
  const ms = d.getTime() - now.getTime()
  return Math.ceil(ms / (1000 * 60 * 60 * 24))
}

function computeDateSanity(rfp) {
  const now = new Date()
  const warnings = []
  const meta = { dates: {} }

  const fields = [
    ['submissionDeadline', 'Submission deadline'],
    ['questionsDeadline', 'Questions deadline'],
    ['bidMeetingDate', 'Bid meeting date'],
    ['bidRegistrationDate', 'Bid registration date'],
    ['projectDeadline', 'Project deadline'],
  ]

  for (const [key, label] of fields) {
    const raw = rfp?.[key]
    const parsed = parseUsDate(raw)
    if (raw && typeof raw === 'string' && raw !== 'Not available' && !parsed) {
      warnings.push(`${label} looks invalid (${raw}).`)
    }
    if (parsed) {
      const du = daysUntil(parsed, now)
      meta.dates[key] = {
        raw,
        iso: parsed.toISOString(),
        daysUntil: du,
        isPast: du !== null ? du < 0 : null,
      }
      // Only hard-warn on submission deadline being past; other dates are informational.
      if (key === 'submissionDeadline' && du !== null && du < 0) {
        warnings.push(`${label} appears past (${raw}).`)
      }
    }
  }

  return { warnings, meta }
}

function checkDisqualification(rfp) {
  const now = new Date()
  const sub = parseUsDate(rfp?.submissionDeadline)
  if (sub && sub < now) return true

  const raw = typeof rfp?.rawText === 'string' ? rfp.rawText.toLowerCase() : ''
  const isMandatoryMeeting =
    raw.includes('mandatory') &&
    (raw.includes('pre-bid') ||
      raw.includes('prebid') ||
      raw.includes('pre-proposal') ||
      raw.includes('preproposal') ||
      raw.includes('site visit') ||
      raw.includes('bid conference') ||
      raw.includes('pre proposal conference'))
  const isMandatoryRegistration =
    raw.includes('mandatory') &&
    (raw.includes('registration') ||
      raw.includes('vendor registration') ||
      raw.includes('bid registration') ||
      raw.includes('register'))

  if (isMandatoryMeeting) {
    const meeting = parseUsDate(rfp?.bidMeetingDate)
    if (meeting && meeting < now) return true
  }
  if (isMandatoryRegistration) {
    const reg = parseUsDate(rfp?.bidRegistrationDate)
    if (reg && reg < now) return true
  }

  return false
}

function computeFitScore(rfp) {
  const now = new Date()
  const reasons = []
  let score = 100

  const raw = typeof rfp?.rawText === 'string' ? rfp.rawText.toLowerCase() : ''
  const sub = parseUsDate(rfp?.submissionDeadline)
  const q = parseUsDate(rfp?.questionsDeadline)
  const meeting = parseUsDate(rfp?.bidMeetingDate)
  const reg = parseUsDate(rfp?.bidRegistrationDate)

  // Hard disqualifier
  if (sub && sub < now) {
    return {
      score: 0,
      reasons: ['Submission deadline passed.'],
      disqualified: true,
    }
  }

  const duSub = sub ? daysUntil(sub, now) : null
  if (typeof duSub === 'number') {
    if (duSub <= 7) {
      score -= 20
      reasons.push(`Due soon (${duSub} days until submission).`)
    } else if (duSub <= 14) {
      score -= 10
      reasons.push(`Moderately urgent (${duSub} days until submission).`)
    }
  }

  const duQ = q ? daysUntil(q, now) : null
  if (typeof duQ === 'number' && duQ < 0) {
    score -= 10
    reasons.push('Questions deadline appears past.')
  }

  const isMandatoryMeeting = raw.includes('mandatory') && raw.includes('pre')
  if (isMandatoryMeeting) {
    if (!meeting) {
      score -= 10
      reasons.push(
        'Mentions mandatory pre-bid meeting but no meeting date found.',
      )
    } else {
      const du = daysUntil(meeting, now)
      if (typeof du === 'number' && du < 0) {
        return {
          score: 0,
          reasons: ['Mandatory meeting appears past.'],
          disqualified: true,
        }
      }
      reasons.push('Mandatory pre-bid meeting detected.')
      score -= 5
    }
  }

  const isMandatoryRegistration =
    raw.includes('mandatory') && raw.includes('register')
  if (isMandatoryRegistration) {
    if (!reg) {
      score -= 10
      reasons.push(
        'Mentions mandatory registration but no registration date found.',
      )
    } else {
      const du = daysUntil(reg, now)
      if (typeof du === 'number' && du < 0) {
        return {
          score: 0,
          reasons: ['Mandatory registration appears past.'],
          disqualified: true,
        }
      }
      reasons.push('Mandatory registration detected.')
      score -= 5
    }
  }

  if (raw.includes('bid bond') || raw.includes('performance bond')) {
    score -= 10
    reasons.push('Bid/performance bond requirements detected.')
  }
  if (
    raw.includes('license') ||
    raw.includes('licensing') ||
    raw.includes('certification')
  ) {
    score -= 5
    reasons.push('Licensing/certification requirements detected.')
  }

  score = Math.max(0, Math.min(100, score))
  if (reasons.length === 0) reasons.push('No major risks detected.')
  return { score, reasons, disqualified: false }
}

module.exports = {
  parseUsDate,
  computeDateSanity,
  checkDisqualification,
  computeFitScore,
}
