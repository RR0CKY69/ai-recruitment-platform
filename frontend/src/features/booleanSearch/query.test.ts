import { describe, expect, it } from 'vitest'
import { generateBooleanQuery } from './query'

const baseInput = {
  title: 'Python Developer',
  description: 'Build APIs using Django and FastAPI.',
  requiredSkills: ['Django', 'FastAPI'],
  includeKeywords: [],
  excludeKeywords: ['Intern'],
  includeOperator: 'OR' as const,
  template: 'job_board' as const,
}

describe('generateBooleanQuery', () => {
  it('quotes the job title and groups include/exclude terms with Boolean operators', () => {
    expect(generateBooleanQuery(baseInput)).toBe(
      '"Python Developer" AND (Django OR FastAPI) NOT (Intern)',
    )
  })

  it('supports AND for includes and quotes multiword phrases', () => {
    expect(generateBooleanQuery({
      ...baseInput,
      includeOperator: 'AND',
      includeKeywords: ['PostgreSQL Database'],
      excludeKeywords: ['Entry Level'],
    })).toBe('"Python Developer" AND (Django AND FastAPI AND "PostgreSQL Database") NOT ("Entry Level")')
  })

  it('builds a Google X-ray query and derives terms from description when requirements are absent', () => {
    expect(generateBooleanQuery({
      ...baseInput,
      requiredSkills: [],
      excludeKeywords: [],
      template: 'google_xray',
    })).toBe('site:linkedin.com/in/ "Python Developer" AND (APIs OR Django OR FastAPI)')
  })

  it('does not make a query for missing information', () => {
    expect(generateBooleanQuery({
      ...baseInput,
      title: '',
      description: '',
      requiredSkills: [],
      excludeKeywords: [],
    })).toBe('')
  })
})
