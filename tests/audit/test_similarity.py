from pathlib import Path

from reverseai.audit.similarity import brand_mentions, code_similarity

ROOT = Path(__file__).resolve().parents[2]
CORPUS = (ROOT / "bench/targets/taskboard/static/app.js").read_text(encoding="utf-8")
FAKE_CLONE = (ROOT / "tests/fixtures/fake_clone/main.py").read_text(encoding="utf-8")


def test_identical_code_scores_one():
    report = code_similarity({"app.js": CORPUS}, [CORPUS])
    assert report.per_file == {"app.js": 1.0}
    assert report.max_score == 1.0
    assert not report.ok


def test_independent_code_scores_low():
    report = code_similarity({"main.py": FAKE_CLONE}, [CORPUS])
    assert report.max_score < 0.05
    assert report.ok
    assert report.threshold == 0.05


def test_partial_copy_scores_fraction_and_short_files_score_zero():
    original = " ".join(f"tok{i}" for i in range(20))
    mixed = original + " " + " ".join(f"own{i}" for i in range(20))
    report = code_similarity(
        {"a.py": mixed, "short.py": "x = 1", "notes.bin": original},
        [original], shingle=4, threshold=0.9,
    )
    assert 0.3 < report.per_file["a.py"] < 0.6
    assert report.per_file["short.py"] == 0.0
    assert "notes.bin" not in report.per_file  # non-text files are not scored
    assert report.ok


def test_no_files_is_ok():
    report = code_similarity({}, [CORPUS])
    assert report.max_score == 0.0 and report.ok


def test_brand_mentions():
    files = {
        "src/a.py": 'x = 1\nTITLE = "Welcome to taskboard PRO"\n',
        "src/b.py": "mytaskboard prod = 2\n",
        "img.png": "TaskBoard Pro",
    }
    assert brand_mentions(files, ["TaskBoard Pro"]) == ["src/a.py:2"]
    assert brand_mentions(files, []) == []


def test_brand_mentions_use_the_barrier_brand_rule():
    files = {
        "main.py": (
            "acme_id = 1\n"
            "class AcmeTasks: ...\n"
            'ROUTE = "/api/task-board/x"\n'
            "TaskBoard = 2\n"
            "pacman = 3\n"
            "taskboarding = 4\n"
        ),
    }
    assert brand_mentions(files, ["Acme", "Task Board"]) == [
        "main.py:1", "main.py:2", "main.py:3", "main.py:4",
    ]
