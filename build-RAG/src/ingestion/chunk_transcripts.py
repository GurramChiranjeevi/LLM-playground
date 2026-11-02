import json
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 3000
CHUNK_OVERLAP = 400

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT /"../"/ "transcripts" / "data"
OUTPUT_DIR = PROJECT_ROOT /"../" / "chunks"
OUTPUT_FILE = OUTPUT_DIR / "chunks.json"


def chunk_file(path: Path, splitter: RecursiveCharacterTextSplitter) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pieces = splitter.split_text(text)

    return [
        {
            "source": path.name,
            "chunk_id": idx,
            "text": piece,
        }
        for idx, piece in enumerate(pieces)
    ]


def main() -> None:
    if not DATA_DIR.is_dir():
        raise SystemExit(f"Data directory not found: {DATA_DIR}")

    txt_files = sorted(DATA_DIR.glob("*.txt"))
    if not txt_files:
        raise SystemExit(f"No .txt files found in {DATA_DIR}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    all_chunks: list[dict] = []
    for file_path in txt_files:
        file_chunks = chunk_file(file_path, splitter)
        all_chunks.extend(file_chunks)
        print(f"  {file_path.name}: {len(file_chunks)} chunks")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(all_chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nFiles processed : {len(txt_files)}")
    print(f"Total chunks    : {len(all_chunks)}")
    print(f"Saved to        : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
