const builtinTemplates = {
  software_development: {
    id: 'software_development',
    name: 'Software Development Proposal',
    projectType: 'software_development',
    sections: [
      { title: 'Title', contentType: 'title', required: true },
      { title: 'Cover Letter', contentType: 'cover_letter', required: true },
      {
        title: 'Firm Qualifications and Experience',
        contentType: 'Firm Qualifications and Experience',
        required: true,
      },
      {
        title: 'Technical Approach & Methodology',
        contentType: 'Technical Approach & Methodology',
        required: true,
        subsections: [
          'Project Initiation & Planning',
          'Technical Architecture',
          'Development Phases',
          'Testing & Quality Assurance',
          'Deployment & Launch',
          'Maintenance & Support',
        ],
      },
      {
        title: 'Key Personnel and Experience',
        contentType: 'Key Personnel and Experience',
        required: true,
        includeRoles: [
          'project_lead',
          'technical_lead',
          'senior_architect',
          'qa_lead',
        ],
      },
      {
        title: 'Budget Estimate',
        contentType: 'Budget Estimate',
        required: true,
        format: 'detailed_table',
      },
      {
        title: 'Project Timeline',
        contentType: 'Project Timeline',
        required: true,
      },
      {
        title: 'References',
        contentType: 'References',
        required: true,
        minimumCount: 3,
        filterByType: 'software_development',
      },
    ],
  },
  strategic_communications: {
    id: 'strategic_communications',
    name: 'Strategic Communications Proposal',
    projectType: 'strategic_communications',
    sections: [
      { title: 'Title', contentType: 'Title', required: true },
      { title: 'Cover Letter', contentType: 'Cover Letter', required: true },
      {
        title: 'Experience & Qualifications',
        contentType: 'Experience & Qualifications',
        required: true,
      },
      {
        title: 'Project Understanding & Workplan',
        contentType: 'Project Understanding & Workplan',
        required: true,
      },
      {
        title: 'Benefits to Client',
        contentType: 'Benefits to Client',
        required: true,
      },
      {
        title: 'Key Team Members',
        contentType: 'Key Team Members',
        required: true,
        includeRoles: [
          'project_manager',
          'communications_lead',
          'content_strategist',
        ],
      },
      { title: 'Budget', contentType: 'Budget', required: true },
      {
        title: 'Compliance & Quality Assurance',
        contentType: 'Compliance & Quality Assurance',
        required: true,
      },
      {
        title: 'References',
        contentType: 'client_references',
        required: true,
        minimumCount: 3,
        filterByType: 'strategic_communications',
      },
    ],
  },
  financial_modeling: {
    id: 'financial_modeling',
    name: 'Financial Modeling & Analysis Proposal',
    projectType: 'financial_modeling',
    sections: [
      { title: 'Title', contentType: 'title', required: true },
      { title: 'Cover Letter', contentType: 'cover_letter', required: true },
      {
        title: 'Firm Qualifications and Experience',
        contentType: 'Firm Qualifications and Experience',
        required: true,
      },
      {
        title: 'Methodology & Approach',
        contentType: 'Methodology & Approach',
        required: true,
      },
      {
        title: 'Team Expertise',
        contentType: 'Key Team Members',
        required: true,
        includeRoles: [
          'financial_analyst',
          'senior_modeler',
          'project_manager',
        ],
      },
      {
        title: 'Deliverables & Timeline',
        contentType: 'Deliverables & Timeline',
        required: true,
      },
      { title: 'Investment & Budget', contentType: 'Budget', required: true },
      {
        title: 'References',
        contentType: 'client_references',
        required: true,
        filterByType: 'financial_modeling',
      },
    ],
  },
}

function getBuiltinTemplate(templateId) {
  return builtinTemplates[String(templateId)]
}

function listBuiltinTemplateSummaries() {
  return Object.values(builtinTemplates).map((t) => ({
    id: t.id,
    name: t.name,
    projectType: t.projectType,
    sectionCount: Array.isArray(t.sections) ? t.sections.length : 0,
    isBuiltin: true,
  }))
}

function toGeneratorTemplate(template) {
  if (!template) return null
  // Convert builtin shape to TemplateGenerator-expected sections array
  if (template.isBuiltin || builtinTemplates[template.id]) {
    return {
      _id: template.id,
      name: template.name,
      projectType: template.projectType,
      sections: (template.sections || []).map((s, idx) => ({
        name: s.title,
        title: s.title,
        contentType: s.contentType || 'static',
        isRequired: s.required !== false,
        order: idx + 1,
        subsections: s.subsections || [],
        includeRoles: s.includeRoles || [],
        minimumCount: s.minimumCount,
        filterByType: s.filterByType,
        format: s.format,
      })),
    }
  }

  // DDB template already matches expected shape
  return template
}

module.exports = {
  builtinTemplates,
  getBuiltinTemplate,
  listBuiltinTemplateSummaries,
  toGeneratorTemplate,
}
