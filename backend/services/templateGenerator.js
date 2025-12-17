const OpenAI = require('openai')
const SharedSectionFormatters = require('./sharedSectionFormatters')
const AIProposalGenerator = require('./aiProposalGenerator')
const promptGuidelines = require('../utils/promptGuidelines')
const { pickTeamMemberBio } = require('./teamMemberProfiles')

class TemplateGenerator {
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

  static async selectRelevantTeamMembers(rfp, teamMembers) {
    const openai = this.openai
    if (!openai || !teamMembers || teamMembers.length === 0) return []
    try {
      const membersSummary = teamMembers.map((member) => ({
        id: member.memberId,
        name: member.nameWithCredentials,
        position: member.position,
        expertise: pickTeamMemberBio(member, rfp?.projectType),
      }))

      const prompt = `Based on the following RFP requirements, select the most relevant team members from our content library. Return ONLY the IDs of the selected members as a JSON array (e.g., ["id1", "id2"]).\n\nRFP Information:\n- Title: ${
        rfp.title
      }\n- Project Type: ${rfp.projectType}\n- Key Requirements: ${
        rfp.keyRequirements?.join(', ') || 'Not specified'
      }\n- Deliverables: ${
        rfp.deliverables?.join(', ') || 'Not specified'
      }\n- Project Scope: ${
        rfp.projectScope || 'Not specified'
      }\n- Raw Text Preview: ${
        rfp.rawText ? rfp.rawText + '...' : 'Not available'
      }\n\nAvailable Team Members:\n${membersSummary
        .map(
          (m) =>
            `ID: ${m.id} | ${m.name} - ${m.position} | Expertise: ${m.expertise}...`,
        )
        .join(
          '\n',
        )}\n\nInstructions:\n- Select team members whose expertise most closely matches the RFP requirements\n- Consider the project type and required skills\n- Limit selection to 2-4 most relevant members\n- If no members are particularly relevant, return an empty array\n- Return only the JSON array of IDs, no other text`

      const completion = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        temperature: 0.1,
        max_tokens: 16000,
        messages: [{ role: 'user', content: prompt }],
      })
      const response = completion.choices[0].message.content.trim()
      const selectedIds = JSON.parse(response)
      return Array.isArray(selectedIds) ? selectedIds : []
    } catch (error) {
      return []
    }
  }

  static async selectRelevantReferences(rfp, references) {
    const openai = this.openai
    if (!openai || !references || references.length === 0) return []
    try {
      const referencesSummary = references.map((ref) => ({
        id: ref._id.toString(),
        organization: ref.organizationName,
        scope: ref.scopeOfWork,
      }))

      const prompt = `Based on the following RFP requirements, select the most relevant project references from our content library. Return ONLY the IDs of the selected references as a JSON array (e.g., ["id1", "id2"]).\n\nRFP Information:\n- Title: ${
        rfp.title
      }\n- Project Type: ${rfp.projectType}\n- Key Requirements: ${
        rfp.keyRequirements?.join(', ') || 'Not specified'
      }\n- Deliverables: ${
        rfp.deliverables?.join(', ') || 'Not specified'
      }\n- Project Scope: ${
        rfp.projectScope || 'Not specified'
      }\n- Raw Text Preview: ${
        rfp.rawText ? rfp.rawText + '...' : 'Not available'
      }\n\nAvailable Project References:\n${referencesSummary
        .map((r) => `ID: ${r.id} | ${r.organization} | Scope: ${r.scope}...`)
        .join(
          '\n',
        )}\n\nInstructions:\n- Select references that demonstrate similar work or capabilities required by this RFP\n- Consider industry, project type, and scope alignment\n- Limit selection to 2-3 most relevant references\n- If no references are particularly relevant, return an empty array\n- Return only the JSON array of IDs, no other text`

      const completion = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        temperature: 0.1,
        max_tokens: 500,
        messages: [{ role: 'user', content: prompt }],
      })
      const response = completion.choices[0].message.content.trim()
      const selectedIds = JSON.parse(response)
      return Array.isArray(selectedIds) ? selectedIds : []
    } catch (error) {
      return []
    }
  }

  static fallbackTeamSelection(rfp, teamMembers) {
    if (!teamMembers || teamMembers.length === 0) return []
    return teamMembers.slice(0, 2).map((m) => m.memberId)
  }

  static fallbackReferenceSelection(rfp, references) {
    if (!references || references.length === 0) return []
    return references.slice(0, 2).map((r) => r._id.toString())
  }

  static async generateAIProposalFromTemplate(rfp, template, customContent) {
    const openai = this.openai
    if (!openai) {
      throw new Error('OpenAI API key not configured')
    }
    if (
      !template ||
      !Array.isArray(template.sections) ||
      template.sections.length === 0
    ) {
      throw new Error('Template missing required sections')
    }

    const companyInfo = await SharedSectionFormatters.fetchCompanyInfo(
      customContent?.companyId || null,
    )
    const teamMembers = await SharedSectionFormatters.fetchTeamMembers()
    const projectReferences =
      await SharedSectionFormatters.fetchProjectReferences()

    let selectedTeamIds = await this.selectRelevantTeamMembers(rfp, teamMembers)
    let selectedReferenceIds = await this.selectRelevantReferences(
      rfp,
      projectReferences,
    )
    if (selectedTeamIds.length === 0 && teamMembers.length > 0) {
      selectedTeamIds = this.fallbackTeamSelection(rfp, teamMembers)
    }
    if (selectedReferenceIds.length === 0 && projectReferences.length > 0) {
      selectedReferenceIds = this.fallbackReferenceSelection(
        rfp,
        projectReferences,
      )
    }

    const templateOrderedSections = [...template.sections]
      .filter((s) => {
        const label =
          s && (s.name || s.title) ? String(s.name || s.title).trim() : ''
        return label.length > 0
      })
      .sort((a, b) => (a.order || 0) - (b.order || 0))

    const compulsory = ['Title', 'Cover Letter']
    const seen = new Set()
    const orderedTitles = []
    ;[
      ...compulsory,
      ...templateOrderedSections.map((s) => String(s.name || s.title).trim()),
    ].forEach((t) => {
      const k = String(t || '').trim()
      const key = k.toLowerCase()
      if (!k || seen.has(key)) return
      seen.add(key)
      orderedTitles.push(k)
    })

    const contentLibrarySections = {}
    const usedLibraryTypes = new Set()
    for (const title of orderedTitles) {
      const libraryType = await SharedSectionFormatters.shouldUseContentLibrary(
        title,
      )
      if (libraryType) {
        if (
          libraryType === 'experience' &&
          usedLibraryTypes.has('experience')
        ) {
          continue
        }
        contentLibrarySections[title] = libraryType
        usedLibraryTypes.add(libraryType)
      }
    }

    const aiOnlySections = orderedTitles.filter(
      (title) => !contentLibrarySections[title],
    )
    const dynamicList = aiOnlySections
      .map((t, i) => `${i + 1}. **${t}**`)
      .join('\n')
    const shouldGenerateCoverLetter = aiOnlySections.includes('Cover Letter')

    const perSectionGuidance = templateOrderedSections
      .map((s) => {
        const hints = []
        if (s.isRequired === true || s.required === true)
          hints.push('Required: Yes')
        const contentType = s.contentType || s.type
        if (contentType) hints.push(`Type: ${contentType}`)
        const baseContent = s.content || s.defaultContent
        if (baseContent && String(baseContent).trim().length > 0) {
          const base = String(baseContent).trim()
          const truncated =
            base.length > 1200 ? `${base.slice(0, 1200)}...` : base
          hints.push(`Base content (use as seed, adapt to RFP):\n${truncated}`)
        }
        return `Section: ${s.name || s.title}\n${hints.join('\n')}`.trim()
      })
      .join('\n\n')

    const coverLetterInstructions = shouldGenerateCoverLetter
      ? `\n\n2. **Cover Letter** - Use company information from content library to create a personalized cover letter\n   Use this EXACT format structure:\n     **Submitted to:** [Client Name from RFP]\n     **Submitted by:** [Company Name from context]\n     **Date:** [Current date in MM/DD/YYYY format]\n\n     Dear [Appropriate salutation based on RFP context],\n\n     [Personalized opening paragraph mentioning specific connections or relevant experience]\n\n     [2-3 body paragraphs explaining understanding of the project and approach]\n\n     [Closing paragraph expressing commitment and looking forward to working together]\n\n     Sincerely,\n\n     [Generated Name], [Generated Title]\n     [Generated Email]\n     [Generated Phone]\n   Generate realistic contact information based on company context and include specific details from the RFP when available.`
      : ''

    const systemPrompt = `You are an expert proposal writer. Generate a comprehensive proposal strictly using the template-provided section titles and the RFP context. \n\nNOTE: Some sections will be handled separately using content library data. Generate content ONLY for the following sections:\n\n${dynamicList}\n\nCRITICAL: Use EXACTLY these section titles as JSON keys, in this order:\n${JSON.stringify(
      aiOnlySections,
    )}${coverLetterInstructions}\n\nFormatting rules:\n- Each JSON value must be markdown-formatted content for that section\n- Do not include any extra keys or wrapper text outside the JSON\n- Use professional, persuasive language\n- **CRITICAL: For Methodology/Process/Phases sections, you MUST use proper markdown table format with 2 columns (Phase | Deliverables)**\n- **CRITICAL: For Budget/Cost sections, you MUST use proper markdown table format with 5 columns (Phase | Role | Hourly Rate | Hours | Cost)**\n- Use <br> tags for line breaks within table cells\n- Keep content grounded in the RFP context; avoid hallucinations\n\nSECTION GUIDELINES:\n${promptGuidelines.getSectionGuidelines()}\n\nTemplate guidance for each non-compulsory section (use as hints, adapt to the RFP):\n${perSectionGuidance}`

    const userPrompt = `RFP Information:\n- Title: ${rfp.title}\n- Client: ${
      rfp.clientName
    }\n- Project Type: ${rfp.projectType}\n- Budget Range: ${
      rfp.budgetRange || 'Not specified'
    }\n- Submission Deadline: ${
      rfp.submissionDeadline || 'Not specified'
    }\n- Project Deadline: ${
      rfp.projectDeadline || 'Not specified'
    }\n- Timeline: ${rfp.timeline || 'Not specified'}\n${
      Array.isArray(rfp.timelineMilestones) && rfp.timelineMilestones.length > 0
        ? `- Timeline Milestones:\n${rfp.timelineMilestones
            .map(
              (m, idx) =>
                `${idx + 1}. ${m?.date || 'Not available'} - ${
                  m?.milestone || ''
                }`,
            )
            .join('\n')}\n`
        : ''
    }- Location: ${rfp.location || 'Not specified'}\n- Key Requirements: ${
      rfp.keyRequirements?.join(', ') || 'Not specified'
    }\n- Deliverables: ${
      rfp.deliverables?.join(', ') || 'Not specified'
    }\n- Contact Information: ${rfp.contactInformation || 'Not specified'}\n\n${
      rfp.attachments && rfp.attachments.length > 0
        ? `RFP Attachments (${rfp.attachments.length} files):\n${rfp.attachments
            .map((att, idx) => {
              let info = `${idx + 1}. ${
                att.originalName
              } (${att.fileType.toUpperCase()}, ${(att.fileSize / 1024).toFixed(
                1,
              )} KB)`
              if (att.description) info += ` - ${att.description}`
              if (att.textContent && att.textContent.trim().length > 0) {
                info += `\n   Content: ${att.textContent.substring(0, 5000)}${
                  att.textContent.length > 5000 ? '... (truncated)' : ''
                }`
              }
              return info
            })
            .join(
              '\n\n',
            )}\n\nNote: The RFP includes these attached documents with their extracted content above. Use this information to create a comprehensive and detailed proposal that addresses all requirements from both the main RFP and the attachments.\n`
        : ''
    }${
      rfp.rawText ? `RFP Full Text:\n${rfp.rawText}` : ''
    }\n\nAdditional Context:\n${
      customContent ? JSON.stringify(customContent) : 'None'
    }`

    try {
      const completion = await openai.chat.completions.create({
        model: 'gpt-4o-mini',
        temperature: 0.3,
        max_tokens: 12000,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt },
        ],
      })

      const raw = completion.choices[0].message.content.trim()

      const buildFallbackTitle = () => {
        const company = 'Not specified'
        const contactBlock = String(rfp.contactInformation || '').trim()
        const emailMatch = contactBlock.match(
          /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i,
        )
        const phoneMatch = contactBlock.match(
          /(?:\+?\d[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}/,
        )
        let name = ''
        if (emailMatch) {
          const before = contactBlock.slice(0, emailMatch.index)
          const nameMatch = before.match(
            /([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s*[,-:]?\s*$/,
          )
          if (nameMatch) name = nameMatch[1].trim()
        }
        return `Submitted by: ${company}\nName: ${
          name || 'Not specified'
        }\nEmail: ${emailMatch ? emailMatch[0] : 'Not specified'}\nNumber: ${
          phoneMatch ? phoneMatch[0] : 'Not specified'
        }`
      }

      try {
        let jsonText = raw
        const jsonMatch = raw.match(/\{[\s\S]*\}/)
        if (jsonMatch) jsonText = jsonMatch[0]
        const parsed = JSON.parse(jsonText)
        const hasExpected = aiOnlySections.some((t) =>
          Object.prototype.hasOwnProperty.call(parsed, t),
        )
        if (hasExpected) {
          if (!parsed.Title || String(parsed.Title).trim().length === 0) {
            parsed.Title = buildFallbackTitle()
          }
          for (const sectionTitle of orderedTitles) {
            const libraryType = contentLibrarySections[sectionTitle]
            if (libraryType) {
              if (libraryType === 'team') {
                parsed[sectionTitle] =
                  SharedSectionFormatters.formatTeamMembersSection(
                    teamMembers,
                    selectedTeamIds,
                    rfp?.projectType || null,
                  )
              } else if (libraryType === 'references') {
                parsed[sectionTitle] =
                  SharedSectionFormatters.formatReferencesSection(
                    projectReferences,
                    selectedReferenceIds,
                  )
              } else if (libraryType === 'title') {
                parsed[sectionTitle] =
                  SharedSectionFormatters.formatTitleSection(companyInfo, rfp)
              } else if (libraryType === 'cover-letter') {
                parsed[sectionTitle] =
                  SharedSectionFormatters.formatCoverLetterSection(
                    companyInfo,
                    rfp,
                  )
              } else if (libraryType === 'experience') {
                parsed[sectionTitle] =
                  await SharedSectionFormatters.formatExperienceSection(
                    companyInfo,
                    rfp,
                  )
              }
            }
          }
          const finalSections = {}
          orderedTitles.forEach((sectionTitle) => {
            if (parsed[sectionTitle]) {
              if (contentLibrarySections[sectionTitle]) {
                const libraryType = contentLibrarySections[sectionTitle]
                let selectedIds = []
                if (libraryType === 'team') selectedIds = selectedTeamIds
                else if (libraryType === 'references')
                  selectedIds = selectedReferenceIds
                const content = parsed[sectionTitle]
                finalSections[sectionTitle] = {
                  content,
                  type: 'content-library',
                  lastModified: new Date().toISOString(),
                  ...(selectedIds.length > 0 && { selectedIds }),
                }
              } else {
                const cleaned = AIProposalGenerator.cleanContent(
                  parsed[sectionTitle],
                )
                finalSections[sectionTitle] = {
                  content: cleaned,
                  type: 'ai-generated',
                  lastModified: new Date().toISOString(),
                }
              }
            }
          })
          return finalSections
        }

        const extracted = AIProposalGenerator.extractSectionsFromMarkdown(raw)
        for (const sectionTitle of orderedTitles) {
          const libraryType = contentLibrarySections[sectionTitle]
          if (libraryType) {
            let content
            let selectedIds = []
            if (libraryType === 'team') {
              content = SharedSectionFormatters.formatTeamMembersSection(
                teamMembers,
                selectedTeamIds,
                rfp?.projectType || null,
              )
              selectedIds = selectedTeamIds
            } else if (libraryType === 'references') {
              content = SharedSectionFormatters.formatReferencesSection(
                projectReferences,
                selectedReferenceIds,
              )
              selectedIds = selectedReferenceIds
            } else if (libraryType === 'title') {
              content = SharedSectionFormatters.formatTitleSection(
                companyInfo,
                rfp,
              )
            } else if (libraryType === 'cover-letter') {
              content = SharedSectionFormatters.formatCoverLetterSection(
                companyInfo,
                rfp,
              )
            } else if (libraryType === 'experience') {
              content = await SharedSectionFormatters.formatExperienceSection(
                companyInfo,
                rfp,
              )
            }
            if (content) {
              extracted[sectionTitle] = {
                content,
                type: 'content-library',
                lastModified: new Date().toISOString(),
                ...(selectedIds.length > 0 && { selectedIds }),
              }
            }
          }
        }
        if (
          !extracted.Title ||
          !extracted.Title.content ||
          (typeof extracted.Title.content === 'object' &&
            !extracted.Title.content.email &&
            !extracted.Title.content.number &&
            !extracted.Title.content.name)
        ) {
          extracted.Title = {
            content: AIProposalGenerator.extractTitleContactInfo(
              buildFallbackTitle(),
            ),
            type: 'ai-generated',
            lastModified: new Date().toISOString(),
          }
        }
        const finalSections = {}
        orderedTitles.forEach((sectionTitle) => {
          if (extracted[sectionTitle])
            finalSections[sectionTitle] = extracted[sectionTitle]
        })
        return finalSections
      } catch (_e) {
        const extracted = AIProposalGenerator.extractSectionsFromMarkdown(raw)
        for (const sectionTitle of orderedTitles) {
          const libraryType = contentLibrarySections[sectionTitle]
          if (libraryType) {
            let content
            let selectedIds = []
            if (libraryType === 'team') {
              content = SharedSectionFormatters.formatTeamMembersSection(
                teamMembers,
                selectedTeamIds,
                rfp?.projectType || null,
              )
              selectedIds = selectedTeamIds
            } else if (libraryType === 'references') {
              content = SharedSectionFormatters.formatReferencesSection(
                projectReferences,
                selectedReferenceIds,
              )
              selectedIds = selectedReferenceIds
            } else if (libraryType === 'title') {
              content = SharedSectionFormatters.formatTitleSection(
                companyInfo,
                rfp,
              )
            } else if (libraryType === 'cover-letter') {
              content = SharedSectionFormatters.formatCoverLetterSection(
                companyInfo,
                rfp,
              )
            } else if (libraryType === 'experience') {
              content = await SharedSectionFormatters.formatExperienceSection(
                companyInfo,
                rfp,
              )
            }
            if (content) {
              extracted[sectionTitle] = {
                content,
                type: 'content-library',
                lastModified: new Date().toISOString(),
                ...(selectedIds.length > 0 && { selectedIds }),
              }
            }
          }
        }
        if (
          !extracted.Title ||
          !extracted.Title.content ||
          (typeof extracted.Title.content === 'object' &&
            !extracted.Title.content.email &&
            !extracted.Title.content.number &&
            !extracted.Title.content.name)
        ) {
          extracted.Title = {
            content: AIProposalGenerator.extractTitleContactInfo(
              buildFallbackTitle(),
            ),
            type: 'ai-generated',
            lastModified: new Date().toISOString(),
          }
        }
        const finalSections = {}
        orderedTitles.forEach((sectionTitle) => {
          if (extracted[sectionTitle])
            finalSections[sectionTitle] = extracted[sectionTitle]
        })
        return finalSections
      }
    } catch (error) {
      console.error('AI template proposal generation failed:', error)
      throw new Error(
        `AI template proposal generation failed: ${error.message}`,
      )
    }
  }
}

module.exports = TemplateGenerator
