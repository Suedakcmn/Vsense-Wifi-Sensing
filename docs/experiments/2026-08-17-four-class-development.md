# Four-class activity-classification development result

## Scope decision

The v1 model contract contains four classes, in this fixed order:

1. `empty_room`
2. `walking`
3. `standing`
4. `desk_work`

The original `sitting` recordings remain in `dataset-v1` but are excluded from
feature generation, subcarrier selection, training, validation, and model
outputs. In the five-class experiments, `sitting` had zero recall in both
development folds: one held-out session was classified as `desk_work`, and the
other as `standing`. The class was removed from the v1 product scope rather
than hiding this failure.

The incompatible class-contract change increments the model schema to version
2.

## Leakage controls

Repeat 3 was not evaluated. Development used two session-held-out directions:

- train/select on r02, validate on r01;
- train/select on r01, validate on r02.

Subcarriers were reselected inside each training side only. Validation data did
not participate in ranking. Pilot, DC/null, and edge indices from the assumed
64-bin project mapping were excluded, and the selected 20 bins were placed in
ascending physical-frequency order before 2D convolution.

The 128-bin mask currently assumes two consecutive 64-bin blocks. This must be
checked against the active ESP-IDF CSI/LTF layout before claiming a physical
pilot/null interpretation.

## Preprocessing and model

- Receivers: `rx_01`, `rx_02`
- Window: 2 seconds
- Stride: 1 second
- Resampling: 40 Hz
- Tensor shape: `[2, 80, 20]`
- Normalization: per-window, per-receiver, per-subcarrier z-score
- Model: small 2D CNN, four output logits
- Optimizer: AdamW
- Loss: inverse-frequency weighted cross entropy
- Model selection: validation macro-F1 with early stopping

## Development results

| Model | Fold r02→r01 | Fold r01→r02 | Mean macro-F1 | Std |
|---|---:|---:|---:|---:|
| kNN, fixed old 20 bins | 0.675 | 0.805 | 0.740 | 0.065 |
| SVM, fixed old 20 bins | 0.680 | 0.914 | 0.797 | 0.117 |
| CNN, training-only selected bins | 0.967 | 0.972 | **0.970** | **0.003** |

CNN fold r02→r01 recalls:

- `empty_room`: 0.886
- `walking`: 0.998
- `standing`: 0.992
- `desk_work`: 0.994

CNN fold r01→r02 recalls:

- `empty_room`: 0.998
- `walking`: 0.984
- `standing`: 0.902
- `desk_work`: 0.989

CPU inference latency was approximately 0.26–0.28 ms per window in these local
runs, far below the one-second stride.

## Honesty and remaining validation

These are development results, not a final generalization claim. Each class has
only one independent session per repeat, and r01/r02 were collected in a
similar room/time campaign. High accuracy may still include day, person,
placement, or session signatures.

The earlier five-class baseline already inspected r03, so r03 is not a fully
unseen final test. Before freezing a final artifact, collect a new day/person
four-class holdout and evaluate it exactly once after model and preprocessing
choices are locked.
