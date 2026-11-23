import torch
import torch.nn as nn


class GRURegressor(nn.Module):
    def __init__(self, input_dim, hidden_dim=128, num_layers=1, dropout=0.2):
        super().__init__()
        self.gru = nn.GRU(
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
        """Returns the fixed-size encoded vector (B, hidden_dim*2), no regression head applied.
        This is what gets saved to CSV and fed into classical regressors afterward."""
        packed = nn.utils.rnn.pack_padded_sequence(
            sequences, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        _, h_n = self.gru(packed)  # GRU returns only h_n (no cell state, unlike LSTM)
        # h_n shape: (num_layers*2, B, hidden_dim) -- take the LAST layer's forward+backward states
        h_forward = h_n[-2]
        h_backward = h_n[-1]
        return torch.cat([h_forward, h_backward], dim=1)  # (B, hidden_dim*2)

    def forward(self, sequences, lengths):
        hidden = self.get_hidden_state(sequences, lengths)
        return self.head(hidden).squeeze(-1)  # (B,) predicted (standardized) score -- used ONLY to train the GRU
