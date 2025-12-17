import {
  UserGroupIcon,
  EyeIcon,
  PencilIcon,
  TrashIcon,
  CheckIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";


export default function TeamSection({ ctx }: { ctx: any }) {
  const {
    team,
    selectedMember,
    setSelectedMember,
    showAddMember,
    setShowAddMember,
    openAddMemberModal,
    memberForm,
    setMemberForm,
    addArrayItem,
    updateArrayItem,
    removeArrayItem,
    handleAddMember,
    handleEditMember,
    editingMember,
    handleSaveMember,
    handleDeleteMember,
  } = ctx;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      {/* Team Members List */}
      <div className="lg:col-span-2">
        <div className="bg-white shadow rounded-lg">
          <div className="px-6 py-5 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Team Members
              </h3>
              <button
                onClick={openAddMemberModal}
                className="inline-flex items-center px-3 py-1 border border-transparent text-xs font-medium rounded text-white bg-primary-600 hover:bg-primary-700"
              >
                + Add Member
              </button>
            </div>
          </div>
          <div className="divide-y divide-gray-200">
            {team.length > 0 ? (
              team.map((member: any, index: number) => (
                <div
                  key={index}
                  className={`px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedMember === member
                      ? "bg-primary-50 border-r-2 border-primary-500"
                      : ""
                  }`}
                  onClick={() => setSelectedMember(member)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-primary-100 flex items-center justify-center">
                        <UserGroupIcon className="h-5 w-5 text-primary-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900">
                          {member.nameWithCredentials || member.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {member.position || member.title}
                        </p>
                      </div>
                    </div>
                    <div className="flex space-x-1">
                      <button
                        onClick={() => setSelectedMember(member)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-primary-600 bg-primary-100 rounded hover:bg-primary-200"
                      >
                        <EyeIcon className="h-3 w-3 mr-1" />
                        View
                      </button>
                      <button
                        onClick={() => handleEditMember(member)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-blue-600 bg-blue-100 rounded hover:bg-blue-200"
                      >
                        <PencilIcon className="h-3 w-3 mr-1" />
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeleteMember(member)}
                        className="inline-flex items-center px-2 py-1 text-xs font-medium text-red-600 bg-red-100 rounded hover:bg-red-200"
                      >
                        <TrashIcon className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="px-6 py-4">
                <p className="text-gray-500 text-sm">No team members found</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Member Details Panel */}
      <div className="lg:col-span-1">
        <div className="bg-white shadow rounded-lg sticky top-6">
          <div className="px-6 py-5 border-b border-gray-200">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              Member Details
            </h3>
          </div>
          <div className="px-6 py-4">
            {selectedMember ? (
              <div className="space-y-4">
                <div className="text-center">
                  <div className="flex-shrink-0 h-16 w-16 rounded-full bg-primary-100 flex items-center justify-center mx-auto mb-3">
                    <UserGroupIcon className="h-8 w-8 text-primary-600" />
                  </div>
                  <h4 className="font-medium text-gray-900">
                    {selectedMember.nameWithCredentials || selectedMember.name}
                  </h4>
                  <p className="text-sm text-gray-500">
                    {selectedMember.position || selectedMember.title}
                  </p>
                  {selectedMember.email && (
                    <a
                      href={`mailto:${selectedMember.email}`}
                      className="text-xs text-primary-600 hover:text-primary-700 hover:underline mt-1 inline-block"
                    >
                      {selectedMember.email}
                    </a>
                  )}
                  {selectedMember.company && (
                    <div className="mt-2 flex items-center justify-center text-xs text-gray-600">
                      <span className="font-medium">Company:</span>
                      <span className="ml-1">
                        {selectedMember.company.name}
                      </span>
                      {selectedMember.company.sharedInfo && (
                        <span className="ml-1" title="Shared company data">
                          🔗
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {selectedMember.biography && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Professional Biography
                    </h5>
                    <div className="text-sm text-gray-600 leading-relaxed">
                      {selectedMember.biography
                        .split("\n")
                        .map((line: string, index: number) => {
                          const trimmedLine = line.trim();
                          if (!trimmedLine) return <br key={index} />;

                          // If line starts with bullet point, render as list item
                          if (
                            trimmedLine.startsWith("•") ||
                            trimmedLine.startsWith("-") ||
                            trimmedLine.startsWith("*")
                          ) {
                            return (
                              <div
                                key={index}
                                className="flex items-start mb-1"
                              >
                                <span className="text-gray-400 mr-2 mt-0.5">
                                  •
                                </span>
                                <span className="flex-1">
                                  {trimmedLine.replace(/^[•\-*]\s*/, "")}
                                </span>
                              </div>
                            );
                          }

                          // Regular paragraph
                          return (
                            <p key={index} className="mb-2">
                              {trimmedLine}
                            </p>
                          );
                        })}
                    </div>
                  </div>
                )}

                {/* Legacy fields for backward compatibility */}
                {selectedMember.experienceYears && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">
                      Experience
                    </h5>
                    <p className="text-sm text-gray-600">
                      {selectedMember.experienceYears}+ years
                    </p>
                  </div>
                )}

                {selectedMember.education &&
                  selectedMember.education.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Education
                      </h5>
                      <ul className="space-y-1">
                        {selectedMember.education.map(
                          (edu: string, index: number) => (
                            <li key={index} className="text-sm text-gray-600">
                              {edu}
                            </li>
                          )
                        )}
                      </ul>
                    </div>
                  )}

                {selectedMember.certifications &&
                  selectedMember.certifications.length > 0 && (
                    <div>
                      <h5 className="text-sm font-medium text-gray-700 mb-2">
                        Certifications
                      </h5>
                      <div className="flex flex-wrap gap-1">
                        {selectedMember.certifications.map(
                          (cert: string, index: number) => (
                            <span
                              key={index}
                              className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded"
                            >
                              {cert}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}
              </div>
            ) : (
              <div className="text-center py-8">
                <UserGroupIcon className="mx-auto h-8 w-8 text-gray-400" />
                <p className="mt-2 text-sm text-gray-500">
                  Select a team member to view their details
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modals moved to page level */}
    </div>
  );
}
