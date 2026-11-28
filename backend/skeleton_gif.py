"""
Fast skeleton GIF.

Draws exactly the same picture as batch_process_subject.plot_skeleton (same colours,
axes, limits, labels and "frame N" title; checked pixel for pixel), but faster:
  1. the plot is built once and only the joint positions move each frame,
     instead of clearing and rebuilding the whole 3D plot every frame;
  2. the frames are split across several CPU processes and drawn at the same time.
The 3D coordinates and the score are not touched; this is only the picture.
"""
import logging
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from io import BytesIO

import numpy as np

log = logging.getLogger("mobiphysio.gif")

# same joint sides as batch_process_subject.py
LEFT_JOINTS = [4, 5, 6, 11, 12, 13]
RIGHT_JOINTS = [1, 2, 3, 14, 15, 16]

_pool = None


def _draw_frames(poses, first_index, parents):
    """Draws a run of frames; returns them as palette images ready for the GIF."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image

    fig = plt.figure(figsize=(6, 6))
    ax = fig.add_subplot(111, projection="3d")
    bones = [(j, p) for j, p in enumerate(parents) if p != -1]
    lines = [ax.plot([0, 0], [0, 0], [0, 0],
                     color="orange" if j in RIGHT_JOINTS else ("green" if j in LEFT_JOINTS else "gray"))[0]
             for j, _ in bones]
    p0 = poses[0]
    dots = ax.scatter(p0[:, 0], p0[:, 2], -p0[:, 1], c="black", s=15)
    ax.set_xlabel("X")
    ax.set_ylabel("Z")
    ax.set_zlabel("Y")
    width, height = fig.canvas.get_width_height()

    out = []
    for k, pose in enumerate(poses):
        for line, (j, p) in zip(lines, bones):
            line.set_data_3d([pose[j, 0], pose[p, 0]], [pose[j, 2], pose[p, 2]], [-pose[j, 1], -pose[p, 1]])
        dots._offsets3d = (pose[:, 0], pose[:, 2], -pose[:, 1])
        r, c = 1.0, pose[0]
        ax.set_xlim3d([c[0] - r, c[0] + r])
        ax.set_ylim3d([c[2] - r, c[2] + r])
        ax.set_zlim3d([-c[1] - r, -c[1] + r])
        ax.set_title(f"frame {first_index + k}")
        # same steps as matplotlib's PillowWriter + Pillow's GIF saver
        buf = BytesIO()
        fig.savefig(buf, format="rgba", dpi=fig.dpi)
        im = Image.frombuffer("RGBA", (width, height), buf.getbuffer(), "raw", "RGBA", 0, 1)
        im = im.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE)
        out.append(im)
    plt.close(fig)
    return out


def _workers(n_frames, wanted):
    if wanted <= 0:
        wanted = max(1, min(6, (os.cpu_count() or 2) - 1))
    return max(1, min(wanted, n_frames // 20 or 1))


def render(pred_3d, parents, gif_path, fps=25, max_frames=0, workers=0):
    """pred_3d: (T, 17, 3) KTPFormer output. Writes the GIF to gif_path."""
    global _pool
    poses = np.asarray(pred_3d)
    if max_frames:
        poses = poses[:max_frames]
    parents = list(parents)
    n = len(poses)
    w = _workers(n, workers)

    frames = None
    if w > 1:
        try:
            if _pool is None:
                _pool = ProcessPoolExecutor(max_workers=w, mp_context=multiprocessing.get_context("spawn"))
            bounds = np.linspace(0, n, w + 1).astype(int)
            futures = [_pool.submit(_draw_frames, poses[a:b], int(a), parents)
                       for a, b in zip(bounds[:-1], bounds[1:]) if b > a]
            frames = [im for f in futures for im in f.result()]
        except Exception as e:  # e.g. processes not allowed: draw in this process instead
            log.warning("Parallel GIF drawing failed (%s); drawing in one process", e)
            _pool = None
            frames = None
    if frames is None:
        frames = _draw_frames(poses, 0, parents)

    frames[0].save(str(gif_path), save_all=True, append_images=frames[1:],
                   duration=int(1000 / fps), loop=0)
