"""Shared activity-classification contract."""

MODEL_SCHEMA_VERSION = 2
CLASS_NAMES = ["empty_room", "walking", "standing", "desk_work"]
EXCLUDED_CLASS_NAMES = ["sitting"]
META_COLUMNS = {"session_id", "subject", "label", "window_start_us", "window_end_us"}
