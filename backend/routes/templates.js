const express = require('express')

const {
  listTemplates,
  getTemplateById,
  createTemplate,
  updateTemplate,
  deleteTemplate,
} = require('../db/templates')

const {
  getBuiltinTemplate,
  listBuiltinTemplateSummaries,
} = require('../services/templatesCatalog')

const router = express.Router()

function isBuiltinTemplateId(id) {
  return !!getBuiltinTemplate(id)
}

// Get all available templates (builtin + DynamoDB)
router.get('/', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1
    const limit = parseInt(req.query.limit) || 20

    const builtin = listBuiltinTemplateSummaries()
    const ddb = (await listTemplates({ limit: 200 }))
      .filter((t) => t && t.isActive !== false)
      .map((t) => ({
        id: t.id,
        name: t.name,
        projectType: t.projectType,
        sectionCount: Array.isArray(t.sections) ? t.sections.length : 0,
        isBuiltin: false,
      }))

    const all = [...builtin, ...ddb]
    const total = all.length
    const pages = Math.max(1, Math.ceil(total / limit))
    const start = (Math.max(1, page) - 1) * limit
    const data = all.slice(start, start + limit)

    res.json({
      data,
      pagination: { page: Math.max(1, page), limit, total, pages },
    })
  } catch (error) {
    console.error('Error fetching templates:', error)
    res.status(500).json({ error: 'Failed to fetch templates' })
  }
})

// Get specific template (builtin or DynamoDB)
router.get('/:templateId', async (req, res) => {
  try {
    const id = String(req.params.templateId)

    const builtin = getBuiltinTemplate(id)
    if (builtin) {
      return res.json({
        id: builtin.id,
        name: builtin.name,
        description: '',
        projectType: builtin.projectType,
        sections: builtin.sections,
        version: 1,
        isActive: true,
        isBuiltin: true,
      })
    }

    const template = await getTemplateById(id)
    if (!template) {
      return res.status(404).json({ error: 'Template not found' })
    }

    res.json({
      id: template.id,
      name: template.name,
      description: template.description,
      projectType: template.projectType,
      sections: template.sections,
      version: template.version,
      isActive: template.isActive,
      createdAt: template.createdAt,
      updatedAt: template.updatedAt,
      isBuiltin: false,
    })
  } catch (error) {
    console.error('Error fetching template:', error)
    res.status(500).json({ error: 'Failed to fetch template' })
  }
})

// Preview template with RFP customization (builtin only)
router.post('/:templateId/preview', async (req, res) => {
  try {
    const template = getBuiltinTemplate(req.params.templateId)

    if (!template) {
      return res.status(404).json({ error: 'Template not found' })
    }

    const rfpData = req.body
    const customizedTemplate = JSON.parse(JSON.stringify(template))

    // Add RFP-specific sections if needed
    if (rfpData.criticalInformation && rfpData.criticalInformation.length > 0) {
      const complianceSection = {
        title: 'Compliance & Critical Information',
        contentType: 'compliance_details',
        required: true,
        criticalInformation: rfpData.criticalInformation,
      }
      customizedTemplate.sections.splice(-1, 0, complianceSection)
    }

    // Adjust budget section format
    const budgetSections = customizedTemplate.sections.filter((s) =>
      String(s.title || '')
        .toLowerCase()
        .includes('budget'),
    )

    for (const section of budgetSections) {
      if (rfpData.budgetType === 'hourly') {
        section.format = 'hourly_breakdown'
      } else if (rfpData.budgetType === 'fixed') {
        section.format = 'fixed_price'
      }
    }

    // Customize team requirements
    if (rfpData.requiredRoles) {
      const teamSections = customizedTemplate.sections.filter(
        (s) => s.contentType === 'team_profiles',
      )

      for (const section of teamSections) {
        section.includeRoles = rfpData.requiredRoles
      }
    }

    res.json(customizedTemplate)
  } catch (error) {
    console.error('Error previewing template:', error)
    res.status(500).json({ error: 'Failed to preview template' })
  }
})

// Update template (DynamoDB-backed)
router.put('/:templateId', async (req, res) => {
  try {
    const templateId = String(req.params.templateId)
    if (isBuiltinTemplateId(templateId)) {
      return res.status(400).json({ error: 'Builtin templates are read-only' })
    }

    const allowedUpdates = [
      'name',
      'description',
      'projectType',
      'sections',
      'isActive',
      'tags',
      'version',
    ]

    const updates = {}
    Object.keys(req.body || {}).forEach((key) => {
      if (allowedUpdates.includes(key)) updates[key] = req.body[key]
    })

    updates.lastModifiedBy = req.user?.id || 'system'

    const updated = await updateTemplate(templateId, updates)
    if (!updated) return res.status(404).json({ error: 'Template not found' })

    res.json({
      id: updated.id,
      name: updated.name,
      description: updated.description,
      projectType: updated.projectType,
      sections: updated.sections,
      version: updated.version,
      isActive: updated.isActive,
      createdAt: updated.createdAt,
      updatedAt: updated.updatedAt,
      isBuiltin: false,
    })
  } catch (error) {
    console.error('Error updating template:', error)
    res.status(500).json({ error: 'Failed to update template' })
  }
})

// Create new template (from builtin structure, stored in DynamoDB)
router.post('/', async (req, res) => {
  try {
    const { name, templateType } = req.body

    if (!name || !templateType) {
      return res
        .status(400)
        .json({ error: 'Missing required fields: name, templateType' })
    }

    const predefined = getBuiltinTemplate(templateType)
    if (!predefined) {
      return res.status(400).json({ error: 'Invalid template type' })
    }

    const templateSections = predefined.sections.map((section, index) => ({
      name: section.title,
      title: section.title,
      content: `Default content for ${section.title}`,
      contentType: section.contentType || 'static',
      isRequired: section.required !== false,
      order: index + 1,
      placeholders: [],
      subsections: section.subsections || [],
      includeRoles: section.includeRoles || [],
    }))

    const created = await createTemplate({
      name,
      description: `Template: ${name}`,
      projectType: predefined.projectType,
      sections: templateSections,
      isActive: true,
      createdBy: 'user',
      lastModifiedBy: 'user',
      version: 1,
    })

    res.status(201).json({
      id: created.id,
      name: created.name,
      description: created.description,
      projectType: created.projectType,
      sections: created.sections,
      version: created.version,
      isActive: created.isActive,
      createdAt: created.createdAt,
      updatedAt: created.updatedAt,
      isBuiltin: false,
    })
  } catch (error) {
    console.error('Error creating template:', error)
    res.status(500).json({ error: 'Failed to create template' })
  }
})

// Delete template (DynamoDB-backed)
router.delete('/:templateId', async (req, res) => {
  try {
    const templateId = String(req.params.templateId)
    if (isBuiltinTemplateId(templateId)) {
      return res
        .status(400)
        .json({ error: 'Builtin templates cannot be deleted' })
    }

    await deleteTemplate(templateId)
    res.json({ message: 'Template deleted successfully' })
  } catch (error) {
    console.error('Error deleting template:', error)
    res.status(500).json({ error: 'Failed to delete template' })
  }
})

module.exports = router
