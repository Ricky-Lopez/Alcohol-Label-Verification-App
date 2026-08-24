# API contracts

`verification.schema.json` is generated from the canonical backend Pydantic models. Frontend
TypeScript declarations are generated from that schema and must not be edited manually.

Regenerate both artifacts after changing a boundary model:

```bash
cd backend
uv run python scripts/export_contract.py

cd ../frontend
npm run generate:contracts
```

The backend contract-drift test fails when the committed JSON Schema does not match the canonical
models. Frontend type checking validates the generated declarations.
