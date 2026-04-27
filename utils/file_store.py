import os
import json

JOB_TRACKER_FILE = "data/job_tracker.json"


def load_job_tracker() -> dict:
    """Loads the job tracker database from disk."""
    if os.path.exists(JOB_TRACKER_FILE):
        with open(JOB_TRACKER_FILE, "r") as f:
            return json.load(f)
    return {"applications": {}}


def save_job_tracker(data: dict) -> None:
    """Saves the job tracker database to disk."""
    with open(JOB_TRACKER_FILE, "w") as f:
        json.dump(data, f, indent=4)
