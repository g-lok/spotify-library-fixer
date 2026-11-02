import io
from spotify_fix.progress import ProgressTracker


def test_progress_tracker_tty():
    stream = io.StringIO()
    # Force interactive mode
    tracker = ProgressTracker("Test Task", 100, enabled=True, stream=stream)
    tracker.update(50, item_info="Item 50")
    tracker.finish("Done")

    output = stream.getvalue()
    assert "\r[Test Task]" in output
    assert "Done" in output


def test_progress_tracker_non_tty():
    stream = io.StringIO()
    # Force non-interactive file redirection mode
    tracker = ProgressTracker("Test Task", 10, enabled=False, stream=stream)
    for i in range(1, 11):
        tracker.update(i)
    tracker.finish("Done")

    output = stream.getvalue()
    assert "[Test Task] Progress:" in output
    assert "Finished in" in output
