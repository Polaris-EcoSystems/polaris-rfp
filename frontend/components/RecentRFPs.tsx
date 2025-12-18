import {
  BuildingOfficeIcon,
  DocumentTextIcon,
  EyeIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { RFP } from '../lib/api'
import Badge from './ui/Badge'
import Button from './ui/Button'
import Card, { CardBody, CardHeader } from './ui/Card'

type RecentRFPsProps = {
  recentRFPs: RFP[]
}

export default function RecentRFPs({ recentRFPs }: RecentRFPsProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg">
              <DocumentTextIcon className="h-6 w-6 text-white" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-gray-900">
                Recent RFPs
              </h3>
              <p className="text-sm text-gray-600">Latest uploaded requests</p>
            </div>
          </div>
          <Button
            as={Link}
            href="/rfps"
            variant="ghost"
            size="sm"
            icon={<EyeIcon className="h-4 w-4" />}
          >
            View All
          </Button>
        </div>
      </CardHeader>
      <CardBody>
        {recentRFPs.length > 0 ? (
          <div className="space-y-4">
            {recentRFPs.map((rfp) => (
              <div
                key={rfp._id}
                className="flex items-center space-x-4 p-3 rounded-xl hover:bg-gradient-to-r hover:from-purple-50 hover:to-pink-50 transition-colors group"
              >
                <div className="w-10 h-10 bg-gradient-to-br from-purple-100 to-pink-100 rounded-lg flex items-center justify-center group-hover:from-purple-200 group-hover:to-pink-200 transition-colors">
                  <DocumentTextIcon className="h-5 w-5 text-purple-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <Link
                    href={`/rfps/${rfp._id}`}
                    className="text-sm font-semibold text-gray-900 hover:text-purple-600 transition-colors"
                  >
                    {rfp.title}
                  </Link>
                  <div className="flex items-center space-x-4 mt-1">
                    <div className="flex items-center text-xs text-gray-500">
                      <BuildingOfficeIcon className="h-4 w-4 mr-1" />
                      {rfp.clientName}
                    </div>
                    <Badge variant="secondary" size="sm">
                      {rfp.projectType?.replace(/_/g, ' ')}
                    </Badge>
                    {rfp.isDisqualified && (
                      <Badge variant="danger" size="sm" pulse>
                        Disqualified
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-300 mb-4" />
            <p className="text-gray-600 font-medium">No RFPs uploaded yet</p>
            <p className="text-gray-500 text-sm mt-1">
              Upload your first RFP to get started
            </p>
            <Button
              as={Link}
              href="/rfps/upload"
              className="mt-4"
              variant="primary"
              gradient
              size="sm"
              icon={<PlusIcon className="h-4 w-4" />}
            >
              Upload RFP
            </Button>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
