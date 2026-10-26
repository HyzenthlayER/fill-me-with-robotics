"""Single source of truth for the original planar robot (SI units)."""

import hashlib
import json
import math

EFFECTORS = ("left_foot", "right_foot", "left_hand", "right_hand")
SPEC = {
    "id": "planar-11",
    "version": "1.0",
    "radius": 0.015,
    "leg_lengths": [0.32, 0.32],
    "arm_lengths": [0.24, 0.22],
    "hip_offsets": [-0.09, 0.09],
    "shoulder_offsets": [-0.08, 0.08],
    "shoulder_height": 0.28,
    "torso_mass": 5.0,
    "leg_masses": [0.8, 0.6],
    "arm_masses": [0.30, 0.25],
    "endpoint_mass": 0.02,
    "torque_limits": [45.0, 45.0, 45.0, 45.0, 18.0, 18.0, 18.0, 18.0],
    "joint_names": [
        "left_hip",
        "left_knee",
        "right_hip",
        "right_knee",
        "left_shoulder",
        "left_elbow",
        "right_shoulder",
        "right_elbow",
    ],
    "joint_limits": [[-2.6, 2.6]] * 8,
    "characteristic_length": 1.0,
}
MODEL_HASH = hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()
Q0 = [
    0.0,
    0.015 + 0.64 * math.cos(0.18),
    0.0,
    0.18,
    -0.36,
    -0.18,
    0.36,
    0.15,
    0.4,
    -0.25,
    -0.4,
]
