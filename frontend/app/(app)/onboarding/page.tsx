'use client'

import { userProfileApi, type UserProfile } from '@/lib/api'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

type StepId = 'basics' | 'certs' | 'resume' | 'review'

type ResumeAsset = NonNullable<UserProfile['resumeAssets']>[number]

function cleanList(input: string): string[] {
  return input
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 50)
}

export default function OnboardingPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [step, setStep] = useState<StepId>('basics')

  const [fullName, setFullName] = useState('')
  const [jobTitles, setJobTitles] = useState<string[]>([])
  const [certifications, setCertifications] = useState<string[]>([])
  const [resumeAssets, setResumeAssets] = useState<ResumeAsset[]>([])

  const [jobTitlesText, setJobTitlesText] = useState('')
  const [certsText, setCertsText] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const resp = await userProfileApi.get()
        const p = resp?.data?.profile
        if (!p) return
        if (cancelled) return
        setFullName(String(p.fullName || '').trim())
        const jt = Array.isArray(p.jobTitles) ? p.jobTitles : []
        const cs = Array.isArray(p.certifications) ? p.certifications : []
        const ra = Array.isArray(p.resumeAssets) ? p.resumeAssets : []
        setJobTitles(jt)
        setCertifications(cs)
        setResumeAssets(ra as any)
        setJobTitlesText(jt.join('\n'))
        setCertsText(cs.join('\n'))
        // Already complete? send them back.
        if (resp?.data?.isComplete) {
          router.replace('/pipeline')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [router])

  const canContinue = useMemo(() => {
    if (step === 'basics') return fullName.trim().length >= 2
    return true
  }, [step, fullName])

  const persistProfile = async () => {
    setSaving(true)
    try {
      const jt = cleanList(jobTitlesText).slice(0, 20)
      const cs = cleanList(certsText).slice(0, 50)
      const payload: Partial<UserProfile> = {
        fullName: fullName.trim() || null,
        jobTitles: jt,
        certifications: cs,
        resumeAssets: resumeAssets as any,
      }
      await userProfileApi.update(payload)
      setJobTitles(jt)
      setCertifications(cs)
    } finally {
      setSaving(false)
    }
  }

  const presignAndUpload = async (file: File) => {
    const fileName = file?.name || 'resume.pdf'
    const contentType = (file?.type || '').toLowerCase()
    const presign = await userProfileApi.presignResume({
      fileName,
      contentType:
        contentType ||
        (fileName.toLowerCase().endsWith('.pdf')
          ? 'application/pdf'
          : 'application/pdf'),
    })
    const putUrl = String((presign as any)?.data?.putUrl || '')
    const asset = (presign as any)?.data?.asset as ResumeAsset | undefined
    if (!putUrl || !asset?.assetId || !asset?.s3Key) {
      throw new Error('Failed to presign resume upload')
    }

    const putRes = await fetch(putUrl, {
      method: 'PUT',
      headers: {
        'Content-Type': String(asset.contentType || contentType || ''),
      },
      body: file,
    })
    if (!putRes.ok) throw new Error(`Upload failed (${putRes.status})`)

    const uploadedAt = new Date().toISOString()
    const next = [
      ...resumeAssets.filter((a) => a?.assetId !== asset.assetId),
      { ...asset, uploadedAt },
    ]
    setResumeAssets(next)
    await userProfileApi.update({ resumeAssets: next as any })
  }

  const complete = async () => {
    setSaving(true)
    try {
      await persistProfile()
      const resp = await userProfileApi.complete()
      const ok = Boolean((resp as any)?.data?.ok)
      if (ok) router.replace('/pipeline')
      else router.replace('/pipeline')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-6">
          <div className="text-sm text-gray-600">Loading onboarding…</div>
        </div>
      </div>
    )
  }

  const StepHeader = ({
    title,
    subtitle,
  }: {
    title: string
    subtitle: string
  }) => (
    <div className="mb-4">
      <div className="text-2xl font-bold text-gray-900">{title}</div>
      <div className="mt-1 text-sm text-gray-600">{subtitle}</div>
    </div>
  )

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900">
              Complete your profile
            </div>
            <div className="text-xs text-gray-600">
              This helps assign work and generate better proposals.
            </div>
          </div>
          <div className="text-xs text-gray-500">
            Step{' '}
            {step === 'basics'
              ? '1'
              : step === 'certs'
              ? '2'
              : step === 'resume'
              ? '3'
              : '4'}{' '}
            / 4
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-200 bg-white shadow-sm p-6">
        {step === 'basics' ? (
          <>
            <StepHeader
              title="Basics"
              subtitle="Tell us who you are and what you do."
            />

            <label className="block text-sm font-medium text-gray-900">
              Full name
            </label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              placeholder="Jane Doe"
            />

            <label className="mt-4 block text-sm font-medium text-gray-900">
              Job title(s)
            </label>
            <textarea
              value={jobTitlesText}
              onChange={(e) => setJobTitlesText(e.target.value)}
              className="mt-1 w-full min-h-[110px] rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              placeholder={'Senior Engineer\nProject Manager'}
            />
            <div className="mt-2 text-xs text-gray-600">
              One per line. We’ll use the first one as your default title.
            </div>
          </>
        ) : null}

        {step === 'certs' ? (
          <>
            <StepHeader
              title="Certifications"
              subtitle="Add any certifications you want to show."
            />
            <textarea
              value={certsText}
              onChange={(e) => setCertsText(e.target.value)}
              className="mt-1 w-full min-h-[160px] rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
              placeholder={'PE\nPMP\nLEED AP'}
            />
            <div className="mt-2 text-xs text-gray-600">One per line.</div>
          </>
        ) : null}

        {step === 'resume' ? (
          <>
            <StepHeader
              title="Resume"
              subtitle="Upload one or more resumes/CVs (PDF/DOC/DOCX)."
            />
            <input
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              multiple
              onChange={async (e) => {
                const files = Array.from(e.target.files || [])
                if (files.length === 0) return
                setSaving(true)
                try {
                  for (const f of files.slice(0, 5)) {
                    await presignAndUpload(f)
                  }
                } finally {
                  setSaving(false)
                  e.target.value = ''
                }
              }}
              className="mt-2 block w-full text-sm"
            />

            <div className="mt-4">
              {resumeAssets.length === 0 ? (
                <div className="text-sm text-gray-600">
                  No resumes uploaded.
                </div>
              ) : (
                <div className="space-y-2">
                  {resumeAssets.slice(0, 10).map((a) => (
                    <div
                      key={a.assetId}
                      className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2"
                    >
                      <div className="text-sm font-medium text-gray-900">
                        {a.fileName || a.assetId}
                      </div>
                      <div className="text-xs text-gray-600">
                        {a.contentType || '—'}
                        {a.uploadedAt ? ` • uploaded ${a.uploadedAt}` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}

        {step === 'review' ? (
          <>
            <StepHeader
              title="Review"
              subtitle="Confirm your details, then complete onboarding."
            />
            <div className="space-y-3 text-sm">
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Full name
                </div>
                <div className="mt-1 text-gray-900">{fullName || '—'}</div>
              </div>
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Job titles
                </div>
                <div className="mt-1 text-gray-900">
                  {jobTitles.length ? jobTitles.join(', ') : '—'}
                </div>
              </div>
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Certifications
                </div>
                <div className="mt-1 text-gray-900">
                  {certifications.length ? certifications.join(', ') : '—'}
                </div>
              </div>
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="text-xs font-semibold text-gray-700">
                  Resumes
                </div>
                <div className="mt-1 text-gray-900">
                  {resumeAssets.length
                    ? `${resumeAssets.length} uploaded`
                    : '—'}
                </div>
              </div>
            </div>
          </>
        ) : null}

        <div className="mt-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              if (step === 'basics') router.replace('/pipeline')
              if (step === 'certs') setStep('basics')
              if (step === 'resume') setStep('certs')
              if (step === 'review') setStep('resume')
            }}
            className="text-sm font-medium px-3 py-2 rounded-md bg-gray-100 hover:bg-gray-200 text-gray-900"
          >
            Back
          </button>

          <div className="flex items-center gap-2">
            {step !== 'review' ? (
              <button
                type="button"
                disabled={!canContinue || saving}
                onClick={async () => {
                  await persistProfile()
                  if (step === 'basics') setStep('certs')
                  else if (step === 'certs') setStep('resume')
                  else if (step === 'resume') setStep('review')
                }}
                className="text-sm font-semibold px-4 py-2 rounded-md bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Continue'}
              </button>
            ) : (
              <button
                type="button"
                disabled={saving}
                onClick={complete}
                className="text-sm font-semibold px-4 py-2 rounded-md bg-primary-600 hover:bg-primary-700 text-white disabled:opacity-50"
              >
                {saving ? 'Completing…' : 'Complete'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
