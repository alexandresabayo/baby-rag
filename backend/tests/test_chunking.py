from app.services.chunking import chunk_text


def test_empty_and_whitespace():
    assert chunk_text("") == []
    assert chunk_text("   \n \n  ") == []


def test_short_paragraph_single_chunk():
    chunks = chunk_text("Hello world.", 100, 10)
    assert len(chunks) == 1
    assert chunks[0]["content"] == "Hello world."
    assert chunks[0]["start_char"] == 0
    assert chunks[0]["end_char"] == len("Hello world.")


def test_paragraph_split():
    text = "First paragraph here.\n\nSecond paragraph there."
    chunks = chunk_text(text, 1000, 150)
    assert len(chunks) == 2
    assert chunks[0]["content"].startswith("First")
    assert chunks[1]["content"].startswith("Second")


def test_offsets_index_original_text():
    text = "One two three.\n\nFour five six.\n\nSeven eight nine."
    chunks = chunk_text(text, 1000, 150)
    for c in chunks:
        assert text[c["start_char"]:c["end_char"]].strip("\n") == c["content"]


def test_huge_paragraph_hard_cut():
    text = ("word " * 5000).strip()
    chunks = chunk_text(text, 1000, 150)
    assert len(chunks) > 1
    assert all(len(c["content"]) <= 1000 for c in chunks)
    assert all(c["content"].strip() for c in chunks)


def test_exact_size_boundary():
    text = "a" * 100
    chunks = chunk_text(text, 100, 20)
    assert len(chunks) == 1
    assert chunks[0]["content"] == text


def test_overlap_present_in_hard_cut():
    text = ("sentence number one. " * 200).strip()
    chunks = chunk_text(text, 200, 50)
    assert len(chunks) >= 2
    # With overlap, consecutive windows share the tail/head text.
    if len(chunks) >= 2 and len(chunks[0]["content"]) == 200:
        assert chunks[1]["content"][:50] == chunks[0]["content"][-50:]


def test_unicode():
    text = "Émile Zola écrivait des romans. " * 20
    chunks = chunk_text(text, 100, 20)
    assert all(c["content"] for c in chunks)


def test_deterministic():
    text = "Some deterministic text.\n\n" + ("filler sentence here. " * 100)
    a = chunk_text(text, 100, 20)
    b = chunk_text(text, 100, 20)
    assert a == b


def test_sentence_grouping_under_chunk_size():
    text = "One. Two. Three. Four. Five."
    chunks = chunk_text(text, 20, 5)
    assert len(chunks) >= 1
    assert all(len(c["content"]) <= 20 for c in chunks)
