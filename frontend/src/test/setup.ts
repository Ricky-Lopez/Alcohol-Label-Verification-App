import '@testing-library/jest-dom/vitest'

Object.defineProperty(URL, 'createObjectURL', {
  configurable: true,
  value: () => 'blob:test-label'
})

Object.defineProperty(URL, 'revokeObjectURL', {
  configurable: true,
  value: () => undefined
})
