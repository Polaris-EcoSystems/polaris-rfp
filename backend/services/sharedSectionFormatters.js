const OpenAI = require('openai')
const {
  getCompanyByCompanyId,
  listCompanies,
  listTeamMembers,
  listProjectReferences,
} = require('../db/content')

class SharedSectionFormatters {
  // Lazy OpenAI initialization
  static get openai() {
    if (!this._openaiInitialized) {
      this._openai = process.env.OPENAI_API_KEY
        ? new OpenAI({ apiKey: process.env.OPENAI_API_KEY })
        : null
      this._openaiInitialized = true
    }
    return this._openai
  }

  /**
   * Replace company names in text to match the current company
   */
  static replaceCompanyName(text, targetCompanyName) {
    if (!text || typeof text !== 'string' || !targetCompanyName) return text

    const companyNames = ['Eighth Generation Consulting', 'Polaris EcoSystems']

    // Replace any occurrence of other company names with the target company's name
    let result = text
    companyNames.forEach((name) => {
      if (name !== targetCompanyName) {
        const regex = new RegExp(name, 'gi')
        result = result.replace(regex, targetCompanyName)
      }
    })

    return result
  }

  /**
   * Replace website URLs in text to match the current company
   */
  static replaceWebsite(text, targetCompanyName) {
    if (!text || typeof text !== 'string' || !targetCompanyName) return text

    // Map company names to their respective websites
    const websiteMap = {
      'Eighth Generation Consulting': 'https://eighthgen.com',
      'Polaris EcoSystems': 'https://polariseco.com',
    }

    // Get all websites
    const websites = Object.values(websiteMap)
    const targetWebsite = websiteMap[targetCompanyName]

    if (!targetWebsite) return text

    let result = text

    // Replace all other websites with the target company's website
    websites.forEach((website) => {
      if (website !== targetWebsite) {
        // Replace with and without protocol
        const withProtocol = new RegExp(
          website.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
          'gi',
        )
        const withoutProtocol = new RegExp(
          website
            .replace('https://', '')
            .replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
          'gi',
        )

        result = result.replace(withProtocol, targetWebsite)
        result = result.replace(
          withoutProtocol,
          targetWebsite.replace('https://', ''),
        )
      }
    })

    return result
  }

  /**
   * Fetch company information from the content library
   */
  static async fetchCompanyInfo(companyId = null) {
    try {
      if (companyId) return await getCompanyByCompanyId(companyId)
      return (await listCompanies({ limit: 1 })).at(0) || null
    } catch (error) {
      console.error('Error fetching company info:', error)
      return null
    }
  }

  /**
   * Fetch team members from the content library
   */
  static async fetchTeamMembers() {
    try {
      const teamMembers = await listTeamMembers({ limit: 500 })
      return teamMembers.filter(
        (m) => m && (m.isActive === undefined || m.isActive === true),
      )
    } catch (error) {
      console.error('Error fetching team members:', error)
      return []
    }
  }

  /**
   * Fetch project references from the content library
   */
  static async fetchProjectReferences() {
    try {
      const references = await listProjectReferences({ limit: 500 })
      return references.filter(
        (r) =>
          r &&
          (r.isActive === undefined || r.isActive === true) &&
          (r.isPublic === undefined || r.isPublic === true),
      )
    } catch (error) {
      console.error('Error fetching project references:', error)
      return []
    }
  }

  /**
   * Format Title section using company information from content library
   */
  static formatTitleSection(companyInfo, rfp) {
    if (!companyInfo) {
      return {
        submittedBy: 'Not specified',
        name: 'Not specified',
        email: 'Not specified',
        number: 'Not specified',
      }
    }

    const submittedBy = companyInfo.name || 'Not specified'
    const contactName =
      companyInfo.primaryContact?.name ||
      (companyInfo.name
        ? `${companyInfo.name.split(' ')[0]} Representative`
        : 'Not specified')
    const contactEmail =
      companyInfo.primaryContact?.email || companyInfo.email || 'Not specified'
    const contactPhone =
      companyInfo.primaryContact?.phone || companyInfo.phone || 'Not specified'

    return {
      submittedBy,
      name: contactName,
      email: contactEmail,
      number: contactPhone,
    }
  }

  /**
   * Format cover letter using company information from content library
   */
  static formatCoverLetterSection(companyInfo, rfp) {
    if (!companyInfo) {
      return 'No company information available in the content library.'
    }

    const currentDate = new Date().toLocaleDateString('en-US')
    const clientName = rfp.clientName || rfp.title || 'Valued Client'
    const salutation = rfp.clientName
      ? `Dear ${rfp.clientName} Team`
      : 'Dear Hiring Manager'

    // Apply company name and website replacement to cover letter content
    let coverLetterContent = this.replaceCompanyName(
      companyInfo.coverLetter ||
        `We are pleased to submit our proposal for your consideration. Our team brings extensive experience and expertise to deliver exceptional results for your project.`,
      companyInfo.name,
    )
    coverLetterContent = this.replaceWebsite(
      coverLetterContent,
      companyInfo.name,
    )

    const contactName = companyInfo.name
      ? `${companyInfo.name.split(' ')[0]} Representative`
      : 'Project Manager'
    const contactTitle = 'Project Director'
    const contactEmail = companyInfo.email || 'contact@company.com'
    const contactPhone = companyInfo.phone || '(555) 123-4567'

    const formattedCoverLetter = `**Submitted to:** ${clientName}
**Submitted by:** ${companyInfo.name || 'Our Company'}
**Date:** ${currentDate}

${salutation},

${coverLetterContent}

Sincerely,

${contactName}, ${contactTitle}
${contactEmail}
${contactPhone}`

    return formattedCoverLetter
  }

  /**
   * Format team members data into proposal section content
   */
  static formatTeamMembersSection(
    teamMembers,
    selectedIds = null,
    projectType = null,
  ) {
    if (!teamMembers || teamMembers.length === 0) {
      return 'No team members available in the content library.'
    }

    const membersToUse = selectedIds
      ? teamMembers.filter((member) => selectedIds.includes(member.memberId))
      : teamMembers

    if (membersToUse.length === 0) {
      return 'No suitable team members found for this project.'
    }

    let content =
      'Our experienced team brings together diverse expertise and proven track record to deliver exceptional results.\n\n'

    membersToUse.forEach((member) => {
      const {
        pickTeamMemberBio,
        pickTeamMemberExperience,
      } = require('./teamMemberProfiles')
      const bio = pickTeamMemberBio(member, projectType)
      const exp = pickTeamMemberExperience(member, projectType)
      content += `**${member.nameWithCredentials}** - ${member.position}\n\n`
      if (bio) content += `${bio}\n\n`
      if (exp) content += `**Relevant experience:**\n\n${exp}\n\n`
    })

    return content.trim()
  }

  /**
   * Format project references data into proposal section content
   */
  static formatReferencesSection(references, selectedIds = null) {
    if (!references || references.length === 0) {
      return 'No project references available in the content library.'
    }

    const referencesToUse = selectedIds
      ? references.filter((reference) =>
          selectedIds.includes(reference._id.toString()),
        )
      : references

    if (referencesToUse.length === 0) {
      return 'No suitable project references found for this project.'
    }

    let content =
      'Below are some of our recent project references that demonstrate our capabilities and client satisfaction:\n\n'

    referencesToUse.forEach((reference) => {
      content += `**${reference.organizationName}**`
      if (reference.timePeriod) {
        content += ` (${reference.timePeriod})`
      }
      content += '\n\n'

      content += `**Contact:** ${reference.contactName}`
      if (reference.contactTitle) {
        content += `, ${reference.contactTitle}`
      }
      if (reference.additionalTitle) {
        content += ` - ${reference.additionalTitle}`
      }
      content += ` of ${reference.organizationName}\n\n`

      if (reference.contactEmail) {
        content += `**Email:** ${reference.contactEmail}\n\n`
      }

      if (reference.contactPhone) {
        content += `**Phone:** ${reference.contactPhone}\n\n`
      }

      content += `**Scope of Work:** ${reference.scopeOfWork}\n\n`
    })

    return content.trim()
  }

  /**
   * Format experience and qualifications using company information from content library
   */
  static async formatExperienceSection(companyInfo, rfp) {
    if (!companyInfo) {
      return 'No company information available in the content library.'
    }

    const openai = this.openai
    if (openai && companyInfo.firmQualificationsAndExperience) {
      try {
        // Apply company name and website replacement before sending to AI
        let replacedContent = this.replaceCompanyName(
          companyInfo.firmQualificationsAndExperience,
          companyInfo.name,
        )
        replacedContent = this.replaceWebsite(replacedContent, companyInfo.name)

        const prompt = `Take the following company qualifications and experience content and format it professionally for an RFP proposal. Keep the formatting simple and clean.

Company Experience Content:
${replacedContent}

RFP Project Context:
- Title: ${rfp.title || 'Not specified'}
- Client: ${rfp.clientName || 'Not specified'}
- Project Type: ${rfp.projectType || 'Not specified'}
- Key Requirements: ${rfp.keyRequirements?.join(', ') || 'Not specified'}

Format this content following these rules:
1. Use the company's content as the primary source - do not add excessive details
2. Keep formatting simple - use hyphens (-) for lists, no markdown headings (#)
3. Write in paragraph form with bullet points for achievements/awards only
4. Make it relevant to the RFP but don't over-elaborate
5. Use professional, concise language
6. Do not add multiple sections or subheadings
7. Keep the same tone and style as the original content

Return only the clean, simply formatted content without markdown headings or excessive structure.`

        const completion = await openai.chat.completions.create({
          model: 'gpt-4o-mini',
          temperature: 0.3,
          max_tokens: 2000,
          messages: [{ role: 'user', content: prompt }],
        })

        const formattedContent = completion.choices[0].message.content.trim()
        return formattedContent
      } catch (error) {
        console.error('AI formatting failed for experience section:', error)
        // Fallback to basic formatting
      }
    }

    // Apply company name and website replacement to base content as well
    let baseContent = this.replaceCompanyName(
      companyInfo.firmQualificationsAndExperience ||
        `${
          companyInfo.name || 'Our company'
        } brings extensive experience and proven qualifications to deliver exceptional results for your project.`,
      companyInfo.name,
    )
    baseContent = this.replaceWebsite(baseContent, companyInfo.name)

    let formattedContent = baseContent

    if (
      companyInfo.statistics &&
      (companyInfo.statistics.yearsInBusiness ||
        companyInfo.statistics.projectsCompleted)
    ) {
      formattedContent += `\n\n`
      if (companyInfo.statistics.yearsInBusiness) {
        formattedContent += `Our company has been in business for ${companyInfo.statistics.yearsInBusiness}+ years`
      }
      if (companyInfo.statistics.projectsCompleted) {
        formattedContent += `${
          companyInfo.statistics.yearsInBusiness
            ? ', completing'
            : 'We have completed'
        } ${companyInfo.statistics.projectsCompleted}+ projects`
      }
      if (companyInfo.statistics.clientsSatisfied) {
        formattedContent += ` for ${companyInfo.statistics.clientsSatisfied}+ satisfied clients`
      }
      formattedContent += `.`
    }

    if (
      companyInfo.coreCapabilities &&
      companyInfo.coreCapabilities.length > 0
    ) {
      formattedContent += `\n\nOur core services include: ${companyInfo.coreCapabilities.join(
        ', ',
      )}.`
    }

    return formattedContent.trim()
  }

  /**
   * Check if a section title indicates it should use content library data
   * Uses OpenAI to intelligently classify section types
   */
  static async shouldUseContentLibrary(sectionTitle) {
    const title = sectionTitle.toLowerCase().trim()
    // Hard rules first (avoid misclassification like "Key Personnel and Experience")
    // Title / cover-page variants
    if (
      title === 'title' ||
      title === 'title page' ||
      title.includes('title page') ||
      title.includes('cover page') ||
      title.includes('cover sheet') ||
      title.includes('title sheet')
    ) {
      return 'title'
    }

    // Cover letter variants
    if (
      title === 'cover letter' ||
      title.includes('cover letter') ||
      title.includes('introduction letter') ||
      title.includes('transmittal letter')
    ) {
      return 'cover-letter'
    }

    // TEAM/PERSONNEL: must win even if "experience" is also present
    if (
      title.includes('personnel') ||
      title.includes('team') ||
      title.includes('staff') ||
      title.includes('key personnel') ||
      title.includes('project team') ||
      title.includes('team member') ||
      title.includes('human resource') ||
      title.includes('resume') ||
      title.includes('resumes') ||
      title.includes('curriculum vitae') ||
      title.includes('cv') ||
      title.includes('bios') ||
      title.includes('biographies') ||
      title.includes('staffing')
    ) {
      return 'team'
    }

    // References / past performance
    if (
      title.includes('reference') ||
      title.includes('past project') ||
      title.includes('past performance') ||
      title.includes('client reference') ||
      title.includes('project portfolio')
    ) {
      return 'references'
    }

    const openai = this.openai
    if (!openai) {
      return this.shouldUseContentLibraryFallback(sectionTitle)
    }

    try {
      const prompt = `Analyze this proposal section title and classify it into one of these categories:
- "title" - for title page/cover page sections
- "cover-letter" - for cover letter, introduction letter, or transmittal letter sections
- "experience" - for company experience, qualifications, capabilities, expertise, technical approach, or methodology sections
- "team" - for personnel, team members, staff, or key personnel sections
- "references" - for project references, past projects, or client references sections
- null - if it doesn't clearly fit any of the above categories

Section title: "${sectionTitle}"

IMPORTANT: If the title contains BOTH personnel/team words AND "experience", you MUST return "team".

Respond with ONLY one of these values: "title", "cover-letter", "experience", "team", "references", or null`

      const completion = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        temperature: 0.1,
        max_tokens: 20,
        messages: [{ role: 'user', content: prompt }],
      })

      const response = completion.choices[0].message.content
        .trim()
        .toLowerCase()

      if (response.includes('title') && !response.includes('cover'))
        return 'title'
      if (
        response.includes('cover-letter') ||
        response.includes('cover letter')
      )
        return 'cover-letter'
      if (response.includes('experience')) return 'experience'
      if (response.includes('team')) return 'team'
      if (response.includes('reference')) return 'references'
      if (response.includes('null') || response === 'null') return null

      console.warn(
        `Unexpected AI response for section "${sectionTitle}": ${response}. Using fallback.`,
      )
      return this.shouldUseContentLibraryFallback(sectionTitle)
    } catch (error) {
      console.error('AI section classification failed:', error)
      return this.shouldUseContentLibraryFallback(sectionTitle)
    }
  }

  /**
   * Fallback keyword-based section classification when AI is unavailable
   */
  static shouldUseContentLibraryFallback(sectionTitle) {
    const title = sectionTitle.toLowerCase()

    // Title / cover-page variants
    if (
      title === 'title' ||
      title === 'title page' ||
      title.includes('title page') ||
      title.includes('cover page') ||
      title.includes('cover sheet') ||
      title.includes('title sheet')
    ) {
      return 'title'
    }

    if (
      title.includes('cover letter') ||
      title.includes('introduction letter') ||
      title.includes('transmittal letter')
    ) {
      return 'cover-letter'
    }

    // TEAM/PERSONNEL: must win even if "experience" is also present
    if (
      title.includes('personnel') ||
      title.includes('team') ||
      title.includes('staff') ||
      title.includes('key personnel') ||
      title.includes('project team') ||
      title.includes('team member') ||
      title.includes('human resource') ||
      title.includes('key personnel and experience') ||
      title.includes('resume') ||
      title.includes('resumes') ||
      title.includes('curriculum vitae') ||
      title.includes('cv') ||
      title.includes('bios') ||
      title.includes('biographies') ||
      title.includes('staffing')
    ) {
      return 'team'
    }

    if (
      title.includes('reference') ||
      title.includes('past project') ||
      title.includes('past performance') ||
      title.includes('client reference') ||
      title.includes('project portfolio')
    ) {
      return 'references'
    }

    if (
      title.includes('experience') ||
      title.includes('qualification') ||
      title.includes('firm qualification') ||
      title.includes('company qualification') ||
      title.includes('firm experience') ||
      title.includes('company experience') ||
      title.includes('background') ||
      title.includes('capabilities') ||
      title.includes('expertise') ||
      title.includes('credentials') ||
      title.includes('track record') ||
      title.includes('company profile') ||
      title.includes('technical approach and methodology')
    ) {
      return 'experience'
    }

    return null
  }
}

module.exports = SharedSectionFormatters
