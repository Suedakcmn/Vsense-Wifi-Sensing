# Four-class CNN development candidate

This artifact is a development candidate for live dashboard and hardware
integration testing. It is **not** the final evaluation model and must not be
reported as a final generalization result.

- Classes: `empty_room`, `walking`, `standing`, `desk_work`
- Training repeat: r01
- Validation repeat: r02
- Validation macro-F1: 0.9724
- Final holdout r03 evaluated: no
- Intended use: verify TorchScript loading, CSI preprocessing, live inference,
  and dashboard display

The candidate was selected from the two development-fold runs because it had
the higher validation macro-F1. Repeat r03 remains locked and was not used for
model, feature, subcarrier, or threshold selection.
