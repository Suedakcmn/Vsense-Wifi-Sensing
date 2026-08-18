"""Adapter for the established scikit-learn activity artifact."""

from activity_model import ActivityModel


class SklearnActivityModel(ActivityModel):
    """Named adapter preserving the existing validated model behavior."""
