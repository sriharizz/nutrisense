"""
NutriSense Temporal Computer Vision Scene Tracker
Maintains a temporal sliding window of detected ingredients across consecutive video frames
to produce stable scene representations and unambiguous disappearance events.
"""
import time
from collections import deque
from typing import List, Dict, Set, Any, Optional, Tuple

class TemporalCVTracker:
    def __init__(self, window_size: int = 5, min_stable_frames: int = 3, conf_threshold: float = 0.40):
        self.window_size = window_size
        self.min_stable_frames = min_stable_frames
        self.conf_threshold = conf_threshold
        
        # Rolling buffer of frame observation sets: deque of (timestamp, set(item_names), dict(item -> conf))
        self.frame_buffer: deque = deque(maxlen=window_size)
        self.stable_scene_set: Set[str] = set()
        self.confidence_map: Dict[str, float] = {}
        self.last_observation_time: float = 0.0

    def add_frame_detections(self, raw_detections: List[Dict[str, Any]], timestamp: Optional[float] = None) -> Set[str]:
        if timestamp is None:
            timestamp = time.time()
        self.last_observation_time = timestamp
        
        # Filter raw boxes by confidence threshold
        frame_items = set()
        frame_confs = {}
        
        for det in raw_detections:
            item = det.get("item", "").lower()
            conf = det.get("confidence", 0.0)
            if item and conf >= self.conf_threshold:
                frame_items.add(item)
                frame_confs[item] = max(frame_confs.get(item, 0.0), conf)
                
        self.frame_buffer.append((timestamp, frame_items, frame_confs))
        
        # Determine temporal consensus: an item is stable if present in >= min_stable_frames of recent window
        item_counts: Dict[str, int] = {}
        item_conf_sum: Dict[str, float] = {}
        
        for _, items, confs in self.frame_buffer:
            for it in items:
                item_counts[it] = item_counts.get(it, 0) + 1
                item_conf_sum[it] = item_conf_sum.get(it, 0.0) + confs.get(it, self.conf_threshold)
                
        new_stable_set = set()
        new_conf_map = {}
        
        threshold = min(self.min_stable_frames, len(self.frame_buffer))
        for it, count in item_counts.items():
            if count >= threshold:
                new_stable_set.add(it)
                new_conf_map[it] = round(item_conf_sum[it] / count, 3)
                
        self.stable_scene_set = new_stable_set
        self.confidence_map = new_conf_map
        return self.stable_scene_set

    def get_stable_scene(self) -> Tuple[Set[str], Dict[str, float]]:
        return set(self.stable_scene_set), dict(self.confidence_map)

    def compute_disappearance(self, reference_scene: Set[str], current_scene: Optional[Set[str]] = None) -> Tuple[List[str], str]:
        """
        Computes set difference: reference_scene - current_scene.
        Returns: (disappeared_list, certainty_status)
        where certainty_status is: 'CERTAIN', 'MULTIPLE_REMOVALS', or 'NO_CHANGE'
        """
        if current_scene is None:
            current_scene = self.stable_scene_set
            
        disappeared = list(reference_scene - current_scene)
        
        if len(disappeared) == 1:
            return disappeared, "CERTAIN"
        elif len(disappeared) > 1:
            return disappeared, "MULTIPLE_REMOVALS"
        else:
            return [], "NO_CHANGE"

    def reset(self):
        self.frame_buffer.clear()
        self.stable_scene_set.clear()
        self.confidence_map.clear()
