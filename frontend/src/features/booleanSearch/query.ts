export type BooleanSearchTemplate = 'linkedin' | 'google_xray' | 'job_board'
export type BooleanOperator = 'AND' | 'OR'

export interface BooleanQueryInput {
  title: string
  description: string
  requiredSkills: string[]
  includeKeywords: string[]
  excludeKeywords: string[]
  includeOperator: BooleanOperator
  template: BooleanSearchTemplate
}

const DESCRIPTION_STOP_WORDS = new Set([
  'about', 'across', 'and', 'are', 'a', 'an', 'as', 'at', 'be', 'by', 'candidate',
  'build', 'building', 'company', 'develop', 'development', 'experience', 'for', 'from', 'have', 'in',
  'include', 'including', 'is', 'job', 'looking', 'must', 'of', 'on', 'or', 'our',
  'platform', 'role', 'skills', 'team', 'that', 'the', 'their', 'this', 'to', 'using',
  'with', 'work', 'years', 'you', 'your',
])

function uniqueTerms(terms: string[]): string[] {
  const seen = new Set<string>()
  return terms
    .map(term => term.trim())
    .filter(term => {
      const key = term.toLocaleLowerCase()
      if (!key || seen.has(key)) return false
      seen.add(key)
      return true
    })
}

function descriptionKeywords(description: string): string[] {
  const counts = new Map<string, number>()
  for (const word of description.match(/\b[A-Za-z][A-Za-z0-9+#]{2,}\b/g) ?? []) {
    const key = word.toLocaleLowerCase()
    if (!DESCRIPTION_STOP_WORDS.has(key)) counts.set(word, (counts.get(word) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 5)
    .map(([word]) => word)
}

function quoteTerm(term: string): string {
  const value = term.trim()
  return /\s/.test(value) ? `"${value.replaceAll('"', '\\"')}"` : value
}

export function generateBooleanQuery(input: BooleanQueryInput): string {
  const title = input.title.trim()
  const titlePart = title ? quoteTerm(title) : ''
  const skills = uniqueTerms([
    ...input.requiredSkills,
    ...(input.requiredSkills.length === 0 ? descriptionKeywords(input.description) : []),
    ...input.includeKeywords,
  ])
  const skillPart = skills.length > 0
    ? `(${skills.map(quoteTerm).join(` ${input.includeOperator} `)})`
    : ''
  const excluded = uniqueTerms(input.excludeKeywords)
  const excludePart = excluded.length > 0
    ? `NOT (${excluded.map(quoteTerm).join(' OR ')})`
    : ''
  const query = [titlePart, skillPart].filter(Boolean).join(' AND ')
  const body = [query, excludePart].filter(Boolean).join(' ')

  if (!body) return ''
  if (input.template === 'google_xray' && body) return `site:linkedin.com/in/ ${body}`
  if (input.template === 'linkedin' && body) return `(${body})`
  return body
}
