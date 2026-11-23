"""
The 9 exercises and the final encoder + keypoints + regressor chosen for each.

The codes (E01 ... E09) are internal keys only: the website sends them and the
model files are named by them. Everything shown to users uses `name`.

`reference` = the final TEST metrics from Yolo26.xlsx (FINAL sheet) /
final_encoder_comparison.csv, to 4 decimals. The startup check must reproduce
these exactly.
"""
from dataclasses import dataclass

from settings import LSTM_DIR, GRU_DIR


@dataclass(frozen=True)
class Exercise:
    code: str
    name: str
    encoder: str        # "LSTM" or "GRU"
    modality: str       # "2d" or "3d"
    regressor: str      # name used in deep_tuning.build_pipelines_demo
    reference: dict     # MAE, RMSE, Pearson, CCC on the test split

    @property
    def folder(self):
        return LSTM_DIR if self.encoder == "LSTM" else GRU_DIR

    @property
    def encoder_weights(self):
        return self.folder / f"{self.encoder.lower()}_model_{self.code}_{self.modality}.pt"

    @property
    def states_csv(self):
        return self.folder / f"{self.encoder.lower()}_states_{self.code}_{self.modality}.csv"

    @property
    def metrics_csv(self):
        return self.folder / f"final_metrics_{self.code}_{self.modality}.csv"

    @property
    def model_label(self):
        return f"{self.encoder} + {self.modality.upper()} keypoints + {self.regressor}"


def _ref(mae, rmse, pearson, ccc):
    return {"MAE": mae, "RMSE": rmse, "Pearson": pearson, "CCC": ccc}


EXERCISES = {
    "E01": Exercise("E01", "Abduction",         "GRU",  "3d", "GBM",          _ref(7.2719, 8.8575, 0.8592, 0.8553)),
    "E02": Exercise("E02", "Adduction",         "LSTM", "3d", "LightGBM",     _ref(21.5073, 25.4239, 0.2717, 0.1266)),
    "E03": Exercise("E03", "Lateral Rotation",  "LSTM", "3d", "GBM",          _ref(15.4306, 20.8807, 0.4870, 0.4115)),
    "E04": Exercise("E04", "Medial Rotation",   "LSTM", "3d", "CatBoost",     _ref(9.5698, 11.1992, -0.2888, -0.0788)),
    "E05": Exercise("E05", "Circumduction",     "LSTM", "3d", "BaggedDT",     _ref(14.4652, 18.0720, 0.7058, 0.6518)),
    "E06": Exercise("E06", "Wrist Extension",   "GRU",  "2d", "BaggedDT",     _ref(7.9382, 10.1234, 0.4152, 0.1668)),
    "E07": Exercise("E07", "Hip Joint Flexion", "GRU",  "3d", "RandomForest", _ref(16.2363, 20.1162, 0.3850, 0.0841)),
    "E08": Exercise("E08", "Lumbar Flexion",    "GRU",  "3d", "CatBoost",     _ref(11.7493, 15.9166, 0.8015, 0.7992)),
    "E09": Exercise("E09", "Back Extension",    "LSTM", "3d", "CatBoost",     _ref(13.0017, 16.9322, 0.9133, 0.8811)),
}
