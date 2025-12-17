function normalizeType(t) {
  return String(t || '')
    .trim()
    .toLowerCase()
}

function getBioProfiles(member) {
  const profiles = member?.bioProfiles
  return Array.isArray(profiles) ? profiles : []
}

function pickProfileForProjectType(member, projectType) {
  const pt = normalizeType(projectType)
  const profiles = getBioProfiles(member)
  if (!pt || profiles.length === 0) return null

  // Prefer explicit match
  for (const p of profiles) {
    const types = Array.isArray(p?.projectTypes) ? p.projectTypes : []
    const match = types.map(normalizeType).includes(pt)
    if (match) return p
  }
  return null
}

function pickTeamMemberBio(member, projectType) {
  const matched = pickProfileForProjectType(member, projectType)
  const bio =
    (matched?.bio && String(matched.bio).trim()) ||
    (member?.biography && String(member.biography).trim()) ||
    ''
  return bio
}

function pickTeamMemberExperience(member, projectType) {
  const matched = pickProfileForProjectType(member, projectType)
  const exp =
    (matched?.experience && String(matched.experience).trim()) ||
    (member?.experience && String(member.experience).trim()) ||
    ''
  return exp
}

module.exports = {
  pickTeamMemberBio,
  pickTeamMemberExperience,
}
