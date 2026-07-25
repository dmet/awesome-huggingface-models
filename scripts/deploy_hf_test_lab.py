"""Deploy the tracked RealEyesVR Test Lab files to its Hugging Face Space."""

from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

REPO_ID = "dmet2/realeyesvr-test-lab"
SOURCE = (
    Path(__file__).resolve().parents[1]
    / "realeyesvr"
    / "hf-spaces"
    / "realeyesvr-test-lab"
)
FILES = (
    "README.md",
    "app.py",
    "mock_data.py",
    "requirements.txt",
    "schema.py",
    "test_schema.py",
)


def main() -> None:
    operations = [
        CommitOperationAdd(path_in_repo=name, path_or_fileobj=SOURCE / name)
        for name in FILES
    ]
    result = HfApi().create_commit(
        repo_id=REPO_ID,
        repo_type="space",
        operations=operations,
        commit_message="Add authenticated mock Test Lab",
    )
    print(f"Published commit: {result.commit_url}")


if __name__ == "__main__":
    main()
