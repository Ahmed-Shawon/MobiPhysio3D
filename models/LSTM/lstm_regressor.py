"""
Step 3 of the pipeline.

Bidirectional LSTM encoder + small regression head, as discussed:
LSTM alone only produces a fixed-size hidden vector -- the Linear head
on top is what actually turns that into a predicted score.

get_hidden_state() is exposed separately so that AFTER training, we can
run every video through the trained model and extract just the hidden
state (not the final score prediction) -- this is what gets saved to
lstm_states_2d.csv / lstm_states_3d.csv in step 4.
"""

import torch
import torch.nn as nn


class LSTMRegressor(nn.Module):
    def __init__(self, input_dim, hidden_dim=128, num_layers=1, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.hidden_dim = hidden_dim
        encoded_dim = hidden_dim * 2  # bidirectional -> forward + backward concatenated

        self.head = nn.Sequential(
            nn.Linear(encoded_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

    def get_hidden_state(self, sequences, lengths):
        """Returns the fixed-size encoded vector (B, hidden_dim*2), no regression head applied."""
        packed = nn.utils.rnn.pack_padded_sequence(
            sequences, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        _, (h_n, _) = self.lstm(packed)
        # h_n shape: (num_layers*2, B, hidden_dim) -- take the LAST layer's forward+backward states
        h_forward = h_n[-2]   # last layer, forward direction
        h_backward = h_n[-1]  # last layer, backward direction
        return torch.cat([h_forward, h_backward], dim=1)  # (B, hidden_dim*2)

    def forward(self, sequences, lengths):
        hidden = self.get_hidden_state(sequences, lengths)
        return self.head(hidden).squeeze(-1)  # (B,) predicted (standardized) score
