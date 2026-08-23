"""
NutriSense Weight Stabilizer Subsystem
Pure median filter for smooth physical load cell streaming.
"""
import time
from collections import deque
import numpy as np

class WeightStabilizer:
    def __init__(self, window_size: int = 3, std_threshold: float = 2.0, min_stable_sec: float = 0.05):
        self.window_size = window_size
        self.std_threshold = std_threshold
        self.min_stable_sec = min_stable_sec
        self.buffer = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)
        self.last_stable_weight = 0.0
        self.is_stable = True

    def add_sample(self, weight_g: float, timestamp: float = None) -> dict:
        if timestamp is None:
            timestamp = time.time()
            
        self.buffer.append(weight_g)
        self.timestamps.append(timestamp)

        # Smooth median filter
        filtered = float(np.median(self.buffer))
        std_dev = float(np.std(self.buffer)) if len(self.buffer) > 1 else 0.0

        self.last_stable_weight = filtered
        self.is_stable = True

        return {
            "weight_g": round(weight_g, 1),
            "filtered_g": round(filtered, 1),
            "is_stable": True,
            "std_dev": round(std_dev, 2),
            "last_stable_weight": round(self.last_stable_weight, 1),
        }
