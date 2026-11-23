import numpy as np
import torch
import torch.nn.functional as F

from common.skeleton import Skeleton
from common.graph_utils import adj_mx_from_skeleton, adj_mx_from_skeleton_temporal
from common.model_ktpformer import KTPFormer
from common.camera import normalize_screen_coordinates


# ============================== CONFIG ==============================
CHECKPOINT_PATH = "checkpoint/s_128_L_7_C_512_H_8_f_243_ktpformer_cpn_ft_h36m_dbb_best_epoch.bin"
INPUT_2D_NPY    = "my_2d_keypoints.npy"   # shape (T, 17, 2), pixel coords
OUTPUT_3D_NPY   = "output_3d.npy"         # where to save the result
IMG_WIDTH       = 1000                    # width of the image/video your 2D keypoints came from
IMG_HEIGHT      = 1000                    # height of the image/video your 2D keypoints came from

NUM_FRAME  = 243   # must match training (-f value used when the checkpoint was trained)
NUM_JOINTS = 17
CS         = 512   # must match training (-cs)
DEPTH      = 7      # must match training (-dep)
NUM_HEADS  = 8      # must match training (-num_heads)
DEVICE     = "cuda" if torch.cuda.is_available() else "cpu"
# ======================================================================


def build_h36m_17j_skeleton():
    """Recreates the exact 17-joint H36M skeleton used at training time,
    without needing data_3d_h36m.npz (this topology is fixed, not data-dependent)."""
    skeleton = Skeleton(
        parents=[-1, 0, 1, 2, 3, 4, 0, 6, 7, 8, 9, 0, 11, 12, 13, 14, 12,
                 16, 17, 18, 19, 20, 19, 22, 12, 24, 25, 26, 27, 28, 27, 30],
        joints_left=[6, 7, 8, 9, 10, 16, 17, 18, 19, 20, 21, 22, 23],
        joints_right=[1, 2, 3, 4, 5, 24, 25, 26, 27, 28, 29, 30, 31])
    skeleton.remove_joints([4, 5, 9, 10, 11, 16, 20, 21, 22, 23, 24, 28, 29, 30, 31])
    skeleton._parents[11] = 8
    skeleton._parents[14] = 8
    return skeleton


def load_model():
    skeleton = build_h36m_17j_skeleton()
    adj = adj_mx_from_skeleton(skeleton)

    temporal_parents = np.arange(NUM_FRAME) - 1  # chain graph: frame i's parent is frame i-1
    adj_temporal = adj_mx_from_skeleton_temporal(NUM_FRAME, temporal_parents)

    model = KTPFormer(adj, adj_temporal, num_frame=NUM_FRAME, num_joints=NUM_JOINTS,
                       in_chans=2, embed_dim_ratio=CS, depth=DEPTH, num_heads=NUM_HEADS,
                       mlp_ratio=2., qkv_bias=True, qk_scale=None, drop_path_rate=0.1)

    checkpoint = torch.load(CHECKPOINT_PATH, map_location=DEVICE, weights_only=False)
    state_dict = checkpoint.get("model_pos", checkpoint)
    state_dict = {(k[7:] if k.startswith("module.") else k): v for k, v in state_dict.items()}
    model.load_state_dict(state_dict)

    model = model.to(DEVICE)
    model.eval()
    return model


def chunk_into_windows(kp_2d, num_frame):
    """Same windowing/padding scheme as eval_data_prepare() in run_ktpformer.py:
    non-overlapping windows of length num_frame, last window right-aligned
    (with edge-replicate padding if the whole sequence is shorter than num_frame)."""
    T = kp_2d.shape[0]
    kp_2d = torch.from_numpy(kp_2d.astype("float32"))

    if T < num_frame:
        pad_right = num_frame - T
        kp_2d_padded = kp_2d.permute(1, 2, 0)                      # (J, C, T)
        kp_2d_padded = F.pad(kp_2d_padded, (0, pad_right), mode="replicate")
        kp_2d_padded = kp_2d_padded.permute(2, 0, 1)                # (num_frame, J, C)
        out_num = 1
        windows = kp_2d_padded.unsqueeze(0)
        return windows, T, 0  # only 1 window, valid content is the first T frames

    out_num = T // num_frame + (1 if T % num_frame != 0 else 0)
    windows = torch.empty(out_num, num_frame, kp_2d.shape[1], kp_2d.shape[2])
    for i in range(out_num - 1):
        windows[i] = kp_2d[i * num_frame: i * num_frame + num_frame]
    windows[-1] = kp_2d[-num_frame:]
    return windows, T, out_num


def reconstruct_full_sequence(pred_windows, T, out_num, num_frame):
    """Inverse of chunk_into_windows: stitches per-window 3D predictions back
    into one (T, 17, 3) sequence, matching the reconstruction logic used for
    --render in run_ktpformer.py."""
    if out_num == 0:  # the "T < num_frame" case
        return pred_windows[0, :T]

    out = np.empty((T, pred_windows.shape[2], pred_windows.shape[3]), dtype=pred_windows.dtype)
    for i in range(out_num - 1):
        out[i * num_frame: i * num_frame + num_frame] = pred_windows[i]
    left = T - (out_num - 1) * num_frame
    out[-left:] = pred_windows[-1, -left:]
    return out


def predict_3d(model, kp_2d_pixels, width, height):
    """
    kp_2d_pixels: np.ndarray (T, 17, 2) in raw pixel coordinates
    returns: np.ndarray (T, 17, 3), root-relative 3D (joint 0 = hip = origin)
    """
    kp_norm = normalize_screen_coordinates(kp_2d_pixels.astype("float32"), w=width, h=height)
    windows, T, out_num = chunk_into_windows(kp_norm, NUM_FRAME)

    with torch.no_grad():
        pred = model(windows.to(DEVICE))          # (num_windows, NUM_FRAME, 17, 3)
    pred = pred.cpu().numpy()

    return reconstruct_full_sequence(pred, T, out_num, NUM_FRAME)
