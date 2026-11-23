import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


class PoseSequenceDataset(Dataset):
    def __init__(self, manifest_df, modality, score_mean=None, score_std=None):
        assert modality in ("2d", "3d")
        self.manifest = manifest_df.reset_index(drop=True)
        self.modality = modality
        self.csv_col = "csv_2d" if modality == "2d" else "csv_3d"
        self.num_features = 34 if modality == "2d" else 51  # 17 joints x (2 or 3) coords

        self.score_mean = score_mean if score_mean is not None else self.manifest["average_score"].mean()
        self.score_std = score_std if score_std is not None else self.manifest["average_score"].std()

    def __len__(self):
        return len(self.manifest)

    def _load_sequence(self, csv_path):
        df = pd.read_csv(csv_path)
        T = int(df["frame"].max()) + 1
        coord_cols = ["x", "y"] if self.modality == "2d" else ["x", "y", "z"]
        num_joints = 17
        arr = df[coord_cols].to_numpy(dtype="float32").reshape(T, num_joints, len(coord_cols))

        # root-center every frame at joint 0 (hip), then scale-normalize by that
        # frame's Frobenius norm -- same normalization applied to BOTH modalities,
        # required so 2D and 3D are on a fair, comparable scale (see prior discussion)
        centered = arr - arr[:, 0:1, :]
        norm = np.sqrt(np.sum(centered ** 2, axis=(1, 2), keepdims=True))
        norm = np.where(norm < 1e-8, 1.0, norm)
        normalized = centered / norm

        return normalized.reshape(T, -1)  # (T, 34) or (T, 51)

    def __getitem__(self, idx):
        row = self.manifest.iloc[idx]
        seq = self._load_sequence(row[self.csv_col])          # (T, num_features), variable T
        raw_score = row["average_score"]
        score = (raw_score - self.score_mean) / (self.score_std + 1e-8)

        return {
            "sequence": torch.from_numpy(seq),                 # (T, num_features)
            "length": seq.shape[0],
            "score": torch.tensor(score, dtype=torch.float32),
            "raw_score": torch.tensor(raw_score, dtype=torch.float32),
            "video_name": row["video_name"],
        }


def collate_variable_length(batch):
    lengths = torch.tensor([item["length"] for item in batch], dtype=torch.long)
    max_len = int(lengths.max())
    num_features = batch[0]["sequence"].shape[1]

    padded = torch.zeros(len(batch), max_len, num_features, dtype=torch.float32)
    mask = torch.zeros(len(batch), max_len, dtype=torch.bool)

    for i, item in enumerate(batch):
        T = item["length"]
        padded[i, :T] = item["sequence"]
        mask[i, :T] = True

    scores = torch.stack([item["score"] for item in batch])
    raw_scores = torch.stack([item["raw_score"] for item in batch])
    video_names = [item["video_name"] for item in batch]

    return {
        "sequences": padded,        # (B, T_max, num_features)
        "lengths": lengths,         # (B,) -- for pack_padded_sequence
        "mask": mask,                # (B, T_max)
        "scores": scores,            # (B,) standardized
        "raw_scores": raw_scores,    # (B,) original scale
        "video_names": video_names,
    }
