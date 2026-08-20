import type { ApplicationRecord } from './api/generated/verification'

export const exampleApplication: ApplicationRecord = {
  schemaVersion: '1.0',
  recordId: 'application-old-tom-001',
  intakeSource: 'ad_hoc',
  beverageType: 'distilled_spirits',
  imported: false,
  expectedLabel: {
    brandName: 'OLD TOM DISTILLERY',
    classTypeDesignation: 'Kentucky Straight Bourbon Whiskey',
    alcoholContent: {
      abvPercent: 45,
      proof: 90
    },
    netContents: {
      value: 750,
      unit: 'mL'
    },
    responsibleParties: [
      {
        name: 'Example Distilling Company',
        address: {
          streetLines: [],
          city: 'Frankfort',
          region: 'KY',
          countryCode: 'US'
        }
      }
    ],
    countryOfOrigin: null,
    appellationOfOrigin: null,
    additionalRequiredStatements: []
  }
}
