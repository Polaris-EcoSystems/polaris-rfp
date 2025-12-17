const mongoose = require('mongoose')


// Cache of an autofilled Canva design for a given proposal/company/template.
// We reuse this design for export/open-in-Canva until the proposal changes.
const canvaProposalDesignSchema = new mongoose.Schema(
  {
    proposalId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Proposal',
      required: true,
      index: true,
    },
    companyId: { type: String, trim: true, required: true, index: true },
    brandTemplateId: { type: String, trim: true, required: true, index: true },
    designId: { type: String, trim: true, required: true },
    // Permanent Canva URL (non-temporary)
    designUrl: { type: String, trim: true, default: '' },
    // Temporary URLs (return navigation) typically valid 30 days
    editUrl: { type: String, trim: true, default: '' },
    viewUrl: { type: String, trim: true, default: '' },
    tempUrlsExpireAt: { type: Date, default: null },

    lastProposalUpdatedAt: { type: Date, required: true },
    lastGeneratedAt: { type: Date, required: true },
  },
  { timestamps: true },
)

canvaProposalDesignSchema.index(
  { proposalId: 1, companyId: 1, brandTemplateId: 1 },
  { unique: true },
)

module.exports = mongoose.model(
  'CanvaProposalDesign',
  canvaProposalDesignSchema,
)
