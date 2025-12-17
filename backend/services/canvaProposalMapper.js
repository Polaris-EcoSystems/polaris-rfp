const { getCompanyByCompanyId } = require('../db/content')
const { getCompanyMapping } = require('../db/canva')

function get(obj, path) {
  if (!obj || !path) return undefined
  const parts = String(path).split('.').filter(Boolean)
  let cur = obj
  for (const p of parts) {
    if (cur && typeof cur === 'object' && p in cur) cur = cur[p]
    else return undefined
  }
  return cur
}

function toText(val) {
  if (val === null || val === undefined) return ''
  if (typeof val === 'string') return val
  if (typeof val === 'number' || typeof val === 'boolean') return String(val)
  try {
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

function guessSourceForKey(key) {
  const k = String(key).toLowerCase()
  if (k.includes('rfp') && k.includes('title')) return 'rfp.title'
  if (k.includes('client')) return 'rfp.clientName'
  if (k.includes('submission') || k.includes('due'))
    return 'rfp.submissionDeadline'
  if (k.includes('proposal') && k.includes('title')) return 'proposal.title'
  if (k.includes('cover') && k.includes('letter'))
    return 'proposal.sections.Cover Letter.content'
  if (k === 'cover_letter' || k === 'coverletter')
    return 'proposal.sections.Cover Letter.content'
  if (k.includes('method')) return 'proposal.sections.Methodology.content'
  if (k.includes('approach')) return 'proposal.sections.Methodology.content'
  if (k.includes('deliverable')) return 'proposal.sections.Deliverables.content'
  if (k.includes('timeline') || k.includes('schedule'))
    return 'proposal.sections.Timeline.content'
  if (k.includes('team') || k.includes('personnel'))
    return 'proposal.sections.Team.content'
  if (k.includes('reference') || k.includes('past_performance'))
    return 'proposal.sections.References.content'
  if (k.includes('executive') && k.includes('summary'))
    return 'proposal.sections.Executive Summary.content'
  if (k.includes('understanding'))
    return 'proposal.sections.Project Understanding.content'
  return null
}

async function loadCompanyForProposal(proposal) {
  const companyId = proposal?.companyId
  if (!companyId) return null
  try {
    const c = await getCompanyByCompanyId(companyId)
    return c || null
  } catch {
    return null
  }
}

async function getCompanyTemplate(companyId) {
  if (!companyId) return null
  const cfg = await getCompanyMapping(companyId)
  return cfg || null
}

function isLikelyAutoFilledKey(
  key,
  fieldType,
  { logo, team, headshots, refs } = {},
) {
  const k = String(key).toLowerCase()
  if (fieldType === 'image') {
    if ((k.includes('logo') || k.includes('company_logo')) && logo) return true
    if (
      /(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(photo|headshot|image)$/.test(
        k,
      )
    ) {
      return true
    }
  }
  if (fieldType === 'text') {
    if (guessSourceForKey(key)) return true
    if (
      /(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(name|bio|biography|position|role|title)$/.test(
        k,
      )
    ) {
      return true
    }
    if (
      /(reference|past_performance)[^0-9]*([0-9]{1,2}).*(title|name|client|scope|description|summary|outcome|results)$/.test(
        k,
      )
    ) {
      return true
    }
  }
  return false
}

function buildDatasetValues({
  datasetDef,
  mapping,
  proposal,
  rfp,
  company,
  companyLogoAssetId,
  teamMembers,
  headshotByMemberId,
  references,
}) {
  const out = {}
  const def = datasetDef && typeof datasetDef === 'object' ? datasetDef : {}
  const map = mapping && typeof mapping === 'object' ? mapping : {}
  const team = Array.isArray(teamMembers) ? teamMembers : []
  const refs = Array.isArray(references) ? references : []
  const headshots =
    headshotByMemberId && typeof headshotByMemberId === 'object'
      ? headshotByMemberId
      : {}
  const logo = String(companyLogoAssetId || '').trim()

  Object.entries(def).forEach(([key, fieldDef]) => {
    const fieldType = String(fieldDef?.type || 'text')
    const m = map[key]

    // Only handle text/image for MVP; skip chart unless explicitly mapped
    if (fieldType === 'chart') return

    let valueObj = null
    if (m && typeof m === 'object') {
      const kind = String(m.kind || '')
      if (kind === 'literal') {
        const v = toText(m.value)
        if (fieldType === 'text' && v) valueObj = { type: 'text', text: v }
      } else if (kind === 'asset') {
        const assetId = String(m.assetId || '').trim()
        if (fieldType === 'image' && assetId)
          valueObj = { type: 'image', asset_id: assetId }
      } else if (kind === 'source') {
        const src = String(m.source || '').trim()
        if (src) {
          const val = src.startsWith('proposal.')
            ? get({ proposal }, src.replace(/^proposal\./, 'proposal.'))
            : src.startsWith('rfp.')
            ? get({ rfp }, src.replace(/^rfp\./, 'rfp.'))
            : src.startsWith('company.')
            ? get({ company }, src.replace(/^company\./, 'company.'))
            : get({ proposal, rfp, company }, src)
          const v = toText(val).trim()
          if (fieldType === 'text' && v) valueObj = { type: 'text', text: v }
          if (fieldType === 'image' && v)
            valueObj = { type: 'image', asset_id: v }
        }
      }
    }

    // Heuristic fallback if not mapped
    if (!valueObj) {
      const src = guessSourceForKey(key)
      if (src) {
        const val = src.startsWith('proposal.')
          ? get({ proposal }, src.replace(/^proposal\./, 'proposal.'))
          : src.startsWith('rfp.')
          ? get({ rfp }, src.replace(/^rfp\./, 'rfp.'))
          : src.startsWith('company.')
          ? get({ company }, src.replace(/^company\./, 'company.'))
          : get({ proposal, rfp, company }, src)
        const v = toText(val).trim()
        if (fieldType === 'text' && v) valueObj = { type: 'text', text: v }
      }
    }

    // Smart autofill for common dataset key patterns (team/ref/logo)
    if (!valueObj) {
      const k = String(key).toLowerCase()

      // Company logo for image fields
      if (
        fieldType === 'image' &&
        logo &&
        (k.includes('logo') || k.includes('company_logo'))
      ) {
        valueObj = { type: 'image', asset_id: logo }
      }

      // Team member fields: team_member_1_name, team_member_1_bio, team_member_1_photo, etc.
      const teamMatch = k.match(
        /(team|personnel|staff|key_personnel)[^0-9]*([0-9]{1,2}).*(name|bio|biography|position|role|title|photo|headshot|image)$/,
      )
      if (teamMatch) {
        const idx = Math.max(0, Number(teamMatch[2]) - 1)
        const suffix = teamMatch[3]
        const member = team[idx]
        if (member) {
          if (fieldType === 'text') {
            if (suffix === 'name')
              valueObj = {
                type: 'text',
                text: toText(member.nameWithCredentials).trim(),
              }
            else if (
              suffix === 'position' ||
              suffix === 'role' ||
              suffix === 'title'
            )
              valueObj = { type: 'text', text: toText(member.position).trim() }
            else if (suffix === 'bio' || suffix === 'biography')
              valueObj = { type: 'text', text: toText(member.biography).trim() }
          }
          if (
            fieldType === 'image' &&
            (suffix === 'photo' || suffix === 'headshot' || suffix === 'image')
          ) {
            const assetId = String(
              headshots[String(member.memberId)] || '',
            ).trim()
            if (assetId) valueObj = { type: 'image', asset_id: assetId }
          }
        }
      }

      // References: reference_1_title, reference_1_description, reference_1_client, etc.
      const refMatch = k.match(
        /(reference|past_performance)[^0-9]*([0-9]{1,2}).*(title|name|client|scope|description|summary|outcome|results)$/,
      )
      if (refMatch && fieldType === 'text') {
        const idx = Math.max(0, Number(refMatch[2]) - 1)
        const suffix = refMatch[3]
        const ref = refs[idx]
        if (ref) {
          if (suffix === 'title' || suffix === 'name')
            valueObj = {
              type: 'text',
              text: toText(ref.title || ref.projectName || '').trim(),
            }
          else if (suffix === 'client')
            valueObj = {
              type: 'text',
              text: toText(ref.clientName || ref.client || '').trim(),
            }
          else if (
            suffix === 'scope' ||
            suffix === 'description' ||
            suffix === 'summary'
          )
            valueObj = {
              type: 'text',
              text: toText(
                ref.description || ref.scope || ref.summary || '',
              ).trim(),
            }
          else if (suffix === 'outcome' || suffix === 'results')
            valueObj = {
              type: 'text',
              text: toText(ref.outcomes || ref.results || '').trim(),
            }
        }
      }
    }

    if (valueObj) out[key] = valueObj
  })

  return out
}

function diagnoseDatasetValues({
  datasetDef,
  mapping,
  proposal,
  rfp,
  company,
  companyLogoAssetId,
  teamMembers,
  headshotByMemberId,
  references,
}) {
  const def = datasetDef && typeof datasetDef === 'object' ? datasetDef : {}
  const map = mapping && typeof mapping === 'object' ? mapping : {}
  const team = Array.isArray(teamMembers) ? teamMembers : []
  const refs = Array.isArray(references) ? references : []
  const headshots =
    headshotByMemberId && typeof headshotByMemberId === 'object'
      ? headshotByMemberId
      : {}
  const logo = String(companyLogoAssetId || '').trim()

  const values = buildDatasetValues({
    datasetDef,
    mapping,
    proposal,
    rfp,
    company,
    companyLogoAssetId,
    teamMembers,
    headshotByMemberId,
    references,
  })

  const results = Object.entries(def).map(([key, fieldDef]) => {
    const fieldType = String(fieldDef?.type || 'text')
    const m = map[key]
    const kind = m && typeof m === 'object' ? String(m.kind || '') : ''
    const v = values[key]
    const hasValue = !!v

    let source = 'blank'
    let reason = ''
    if (hasValue) {
      source = kind ? 'mapped' : 'auto'
    } else {
      if (fieldType === 'chart') {
        source = 'unsupported'
        reason = 'Chart fields are not supported yet.'
      } else if (kind) {
        source = 'mapped'
        reason =
          fieldType === 'image'
            ? 'Mapping selected but asset_id missing or invalid.'
            : 'Mapping selected but source/literal produced empty value.'
      } else if (
        isLikelyAutoFilledKey(key, fieldType, { logo, team, headshots, refs })
      ) {
        source = 'auto'
        if (
          fieldType === 'image' &&
          (String(key).toLowerCase().includes('logo') ||
            String(key).toLowerCase().includes('company_logo')) &&
          !logo
        ) {
          reason = 'Company logo asset_id not found (upload logo).'
        } else if (fieldType === 'image') {
          reason = 'Auto-fill needs selected team members + uploaded headshots.'
        } else {
          reason = 'Auto-fill depends on proposal content library selections.'
        }
      } else {
        reason = 'No mapping set for this field.'
      }
    }

    const preview =
      v?.type === 'text'
        ? String(v.text || '').slice(0, 140)
        : v?.type === 'image'
        ? String(v.asset_id || '')
        : ''

    return {
      key,
      fieldType,
      source,
      filled: hasValue,
      preview,
      reason,
      mapping: kind ? { kind, source: m?.source, assetId: m?.assetId } : null,
    }
  })

  const totals = {
    total: results.length,
    filled: results.filter((r) => r.filled).length,
    blank: results.filter((r) => !r.filled && r.source !== 'unsupported')
      .length,
    unsupported: results.filter((r) => r.source === 'unsupported').length,
  }

  return { totals, results }
}

module.exports = {
  getCompanyTemplate,
  loadCompanyForProposal,
  buildDatasetValues,
  diagnoseDatasetValues,
}
