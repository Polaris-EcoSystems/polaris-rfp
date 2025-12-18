import {
  CalendarDaysIcon,
  EyeIcon,
  RocketLaunchIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { Proposal } from '../lib/api'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Card, { CardBody, CardHeader } from './ui/Card'

type RecentProposalsProps = {
  recentProposals: Proposal[]
}

export default function RecentProposals({
  recentProposals,
}: RecentProposalsProps) {
  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'draft':
        return 'warning'
      case 'submitted':
        return 'success'
      case 'in_review':
        return 'info'
      default:
        return 'secondary'
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-gradient-to-r from-green-500 to-emerald-500 rounded-lg">
              <RocketLaunchIcon className="h-6 w-6 text-white" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-gray-900">
                Recent Proposals
              </h3>
              <p className="text-sm text-gray-600">
                Latest proposal submissions
              </p>
            </div>
          </div>
          <Button
            as={Link}
            href="/proposals"
            variant="ghost"
            size="sm"
            icon={<EyeIcon className="h-4 w-4" />}
          >
            View All
          </Button>
        </div>
      </CardHeader>
      <CardBody>
        {recentProposals.length > 0 ? (
          <div className="space-y-4">
            {recentProposals.map((proposal) => (
              <div
                key={proposal._id}
                className="flex items-center space-x-4 p-3 rounded-xl hover:bg-gradient-to-r hover:from-green-50 hover:to-emerald-50 transition-colors group"
              >
                <div className="w-10 h-10 bg-gradient-to-br from-green-100 to-emerald-100 rounded-lg flex items-center justify-center group-hover:from-green-200 group-hover:to-emerald-200 transition-colors">
                  <RocketLaunchIcon className="h-5 w-5 text-green-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/proposals/${proposal._id}`}
                    className="text-sm font-semibold text-gray-900 hover:text-green-600 transition-colors"
                  >
                    {proposal.title}
                  </Link>
                  <div className="flex items-center space-x-4 mt-1">
                    <Badge
                      variant={getStatusVariant(proposal.status)}
                      size="sm"
                    >
                      {proposal.status}
                    </Badge>
                    <div className="flex items-center text-xs text-gray-500">
                      <CalendarDaysIcon className="h-4 w-4 mr-1" />
                      {new Date(proposal.updatedAt).toLocaleDateString()}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <RocketLaunchIcon className="mx-auto h-12 w-12 text-gray-300 mb-4" />
            <p className="text-gray-600 font-medium">
              No proposals created yet
            </p>
            <p className="text-gray-500 text-sm mt-1">
              Create your first proposal from an RFP
            </p>
            <Button
              as={Link}
              href="/proposals"
              className="mt-4"
              variant="success"
              gradient
              size="sm"
              icon={<RocketLaunchIcon className="h-4 w-4" />}
            >
              Create Proposal
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
