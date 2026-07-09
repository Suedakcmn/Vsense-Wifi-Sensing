# CSI Analysis Workflow

## Purpose

This document explains how to run the Week 1 CSI analysis pipeline using recorded/provided CSI Parquet data.

## Setup

From the repository root:

    cd server
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cd ..

## Expected Input

Place the provided CSI Parquet file under data/.

Example:

    data/csi_final.parquet

Parquet files are ignored by Git and should not be committed.

## Run Analysis

From the repository root:

    python server/analyze_recording.py data/csi_final.parquet

If the dataset contains multiple recordings and has a file_name column:

    python server/analyze_recording.py data/csi_final.parquet --file-name user4-6-1-1-1-r2.dat

## Outputs

Generated figures are saved under:

    outputs/

Expected outputs:

    outputs/csi_analysis_heatmap.png
    outputs/csi_analysis_motion_score.png

## What The Script Does

1. Reads the Parquet file.
2. Prints row count and column names.
3. Builds an amplitude matrix.
4. Saves a CSI heatmap.
5. Computes a simple motion score using rolling variance.
6. Computes a dynamic threshold.
7. Applies debounce filtering to reduce short noise spikes.
8. Saves a motion score plot.

## Notes

This is a Week 1 baseline analysis pipeline.

It is not the final ML model.

Future B-role work should compare empty-room and motion-room recordings, improve thresholding, and later move toward feature extraction and classification.

## Local Test Result

The analysis pipeline was tested with a local `csi_final.parquet` file.

Because the original file is large, smaller local samples were created:

    data/csi_sample_5k.parquet
    data/csi_sample_20k.parquet

The following commands were tested:

    python server/analyze_recording.py data/csi_sample_5k.parquet --prefix sample_5k
    python server/analyze_recording.py data/csi_sample_20k.parquet --prefix sample_20k

Generated outputs:

    outputs/sample_5k_heatmap.png
    outputs/sample_5k_motion_score.png
    outputs/sample_20k_heatmap.png
    outputs/sample_20k_motion_score.png

The heatmap and motion score figures were successfully generated locally.

Note:

The tested dataset contains `csi_amplitude`, not raw `csi`.
