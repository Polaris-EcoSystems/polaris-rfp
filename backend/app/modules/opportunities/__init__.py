"""
Opportunity module.

Opportunity is the primary aggregate for the end-to-end pipeline:
Find -> Review -> Proposal -> Submit -> Contract -> Delivery.

Note: For backward compatibility, the initial implementation uses
`opportunity_id == rfp_id` so we can co-exist with the existing
OpportunityState records keyed by `pk=OPPORTUNITY#{rfp_id}`.
"""


