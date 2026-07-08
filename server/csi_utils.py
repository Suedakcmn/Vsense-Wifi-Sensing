import numpy as np


def csi_to_amplitude(csi_values):
    """
    Convert raw CSI int8 list in [imag0, real0, imag1, real1, ...] format
    into amplitude values.

    amplitude = sqrt(real^2 + imag^2)
    """
    arr = np.array(csi_values, dtype=np.float32)

    imag = arr[0::2]
    real = arr[1::2]

    amplitude = np.sqrt(real**2 + imag**2)
    return amplitude