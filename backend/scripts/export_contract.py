import json
from pathlib import Path

from app.models import VerificationContract

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPOSITORY_ROOT / "contracts" / "verification.schema.json"


def build_schema() -> dict[str, object]:
    schema = VerificationContract.model_json_schema(mode="serialization")
    schema["$id"] = "https://alcohol-label-verification.local/contracts/verification.schema.json"
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def main() -> None:
    CONTRACT_PATH.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
