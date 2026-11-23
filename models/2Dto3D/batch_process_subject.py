import os
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
from matplotlib.animation import FuncAnimation

import infer_2d_to_3d as inf


# ============================== CONFIG (defaults, overridable via CLI) ==============================
KEYPOINTS_2D_NPZ   = "data/data_2d_h36m_cpn_ft_h36m_dbb.npz"
SUBJECT            = "S9"
CAMERA_IDX         = 0            # which of the 4 camera views to use, 0-3
OUTPUT_ROOT        = "batch_output"   # everything goes under batch_output/<action_name>/
MAX_FRAMES_FOR_GIF = 150          # cap gif length per action so it renders quickly; None = full length
# ======================================================================================================


LEFT_JOINTS = [4, 5, 6, 11, 12, 13]   # matches keypoints_symmetry left side in the 17-joint layout
RIGHT_JOINTS = [1, 2, 3, 14, 15, 16]


def parse_args():
    p = argparse.ArgumentParser(description="Batch 2D->3D + skeleton visualization for one H36M subject")
    p.add_argument("--subject", default=SUBJECT, help=f"H36M subject, e.g. S1/S5/S6/S7/S8/S9/S11 (default: {SUBJECT})")
    p.add_argument("--camera", type=int, default=CAMERA_IDX, help=f"camera index 0-3 (default: {CAMERA_IDX})")
    p.add_argument("--keypoints-npz", default=KEYPOINTS_2D_NPZ, help=f"path to 2D keypoints npz (default: {KEYPOINTS_2D_NPZ})")
    p.add_argument("--output-root", default=OUTPUT_ROOT, help=f"output folder root (default: {OUTPUT_ROOT})")
    p.add_argument("--checkpoint", default=None, help="override CHECKPOINT_PATH from infer_2d_to_3d.py")
    p.add_argument("--img-width", type=int, default=None, help="override IMG_WIDTH from infer_2d_to_3d.py")
    p.add_argument("--img-height", type=int, default=None, help="override IMG_HEIGHT from infer_2d_to_3d.py")
    p.add_argument("--max-gif-frames", type=int, default=MAX_FRAMES_FOR_GIF,
                   help=f"cap frames per gif, 0 = unlimited (default: {MAX_FRAMES_FOR_GIF})")
    p.add_argument("--no-gif", action="store_true", help="skip gif generation (still saves .npy and frame0.png)")
    p.add_argument("--actions", default=None,
                   help="comma-separated subset of actions to process, e.g. 'Walking 1,Greeting' (default: all)")
    args, _unknown = p.parse_known_args()   # tolerate Jupyter/Kaggle kernel's injected -f argument
    return args


def plot_skeleton(ax, pose, parents):
    ax.clear()
    for j, parent in enumerate(parents):
        if parent == -1:
            continue
        xs = [pose[j, 0], pose[parent, 0]]
        ys = [-pose[j, 1], -pose[parent, 1]]   # negated so head is up, not down
        zs = [pose[j, 2], pose[parent, 2]]
        color = "orange" if j in RIGHT_JOINTS else ("green" if j in LEFT_JOINTS else "gray")
        ax.plot(xs, zs, ys, color=color)  # plotted as (x, z, y) so "up" looks up on screen

    ax.scatter(pose[:, 0], pose[:, 2], -pose[:, 1], c="black", s=15)  # negated to match

    r = 1.0
    center = pose[0]  # hip/root
    ax.set_xlim3d([center[0] - r, center[0] + r])
    ax.set_ylim3d([center[2] - r, center[2] + r])
    ax.set_zlim3d([-center[1] - r, -center[1] + r])  # negated to match
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y")


def safe_name(action_name):
    """Turn 'Walking 1' into 'Walking_1' so it's a clean folder name."""
    return action_name.replace(" ", "_")


def process_one_action(model, skeleton_parents, action_name, clip_2d, out_dir, img_width, img_height,
                        make_gif, max_gif_frames):
    os.makedirs(out_dir, exist_ok=True)

    # 1. inference: 2D -> 3D
    pred_3d = inf.predict_3d(model, clip_2d, img_width, img_height)
    np.save(os.path.join(out_dir, "output_3d.npy"), pred_3d)

    # 2. single-frame skeleton photo
    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    plot_skeleton(ax, pred_3d[0], skeleton_parents)
    ax.set_title(f"{action_name} - frame 0")
    fig.savefig(os.path.join(out_dir, "skeleton_frame0.png"), dpi=120)
    plt.close(fig)

    # 3. animated skeleton gif
    if make_gif:
        n_frames = pred_3d.shape[0]
        if max_gif_frames:
            n_frames = min(n_frames, max_gif_frames)

        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_subplot(111, projection="3d")

        def update(i):
            plot_skeleton(ax, pred_3d[i], skeleton_parents)
            ax.set_title(f"{action_name} - frame {i}")

        anim = FuncAnimation(fig, update, frames=n_frames, interval=1000 / 25)
        anim.save(os.path.join(out_dir, "skeleton_animation.gif"), writer="pillow", fps=25)
        plt.close(fig)

    return pred_3d.shape


if __name__ == "__main__":
    args = parse_args()

    # Apply CLI overrides onto infer_2d_to_3d's config, if given
    if args.checkpoint is not None:
        inf.CHECKPOINT_PATH = args.checkpoint
    if args.img_width is not None:
        inf.IMG_WIDTH = args.img_width
    if args.img_height is not None:
        inf.IMG_HEIGHT = args.img_height

    print(f"Subject: {args.subject} | Camera: {args.camera} | Checkpoint: {inf.CHECKPOINT_PATH}")
    print(f"IMG_WIDTH={inf.IMG_WIDTH} IMG_HEIGHT={inf.IMG_HEIGHT} | Output root: {args.output_root}")

    print("Loading model...")
    model = inf.load_model()
    skeleton = inf.build_h36m_17j_skeleton()
    parents = skeleton.parents()

    print(f"Loading 2D keypoints from {args.keypoints_npz} ...")
    d = np.load(args.keypoints_npz, allow_pickle=True)
    kp = d["positions_2d"].item()

    if args.subject not in kp:
        raise ValueError(f"Subject '{args.subject}' not found. Available: {sorted(kp.keys())}")

    all_actions = sorted(kp[args.subject].keys())
    if args.actions is not None:
        wanted = [a.strip() for a in args.actions.split(",")]
        missing = [a for a in wanted if a not in all_actions]
        if missing:
            raise ValueError(f"Action(s) not found for {args.subject}: {missing}. Available: {all_actions}")
        actions = wanted
    else:
        actions = all_actions

    print(f"Processing {len(actions)} action(s) for {args.subject}: {actions}")

    os.makedirs(args.output_root, exist_ok=True)
    max_gif_frames = None if args.max_gif_frames == 0 else args.max_gif_frames

    for action_name in actions:
        clip_2d = kp[args.subject][action_name][args.camera]   # (T, 17, 2)
        out_dir = os.path.join(args.output_root, safe_name(action_name))
        print(f"Processing {args.subject} / {action_name} (T={clip_2d.shape[0]}) -> {out_dir}")
        shape = process_one_action(model, parents, action_name, clip_2d, out_dir,
                                    inf.IMG_WIDTH, inf.IMG_HEIGHT, not args.no_gif, max_gif_frames)
        print(f"  done, output_3d shape {shape}")

    print(f"\nAll {len(actions)} action(s) done. Results under: {args.output_root}/<action_name>/")
