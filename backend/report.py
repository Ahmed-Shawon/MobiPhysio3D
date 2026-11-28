"""PDF assessment report (fpdf2). One A4 page: exercise, date, score and what it means,
the model used, the details table and key frames of the video next to the skeleton."""
import time
from datetime import datetime

from fpdf import FPDF

from routing import EXERCISES

INK = (11, 16, 32)
BODY = (71, 84, 103)
MUTED = (102, 112, 133)
TEAL = (15, 118, 110)
LINE = (228, 231, 236)
NIGHT = (14, 12, 43)

# What a score means. A rough guide shown next to the number.
BANDS = [
    (80, "Good", "The movement is close to the reference performance for this exercise."),
    (50, "Fair", "The movement is partly correct. Some parts of it differ from the reference performance."),
    (0, "Needs work", "The movement differs clearly from the reference performance for this exercise."),
]


def score_meaning(score):
    for low, label, text in BANDS:
        if score >= low:
            return label, text
    return BANDS[-1][1], BANDS[-1][2]


def model_combo(ex):
    return f"{ex.encoder} + {ex.regressor}, {ex.modality.upper()}"


def _t(s):
    """Core PDF fonts are Latin-1 only; swap the few characters that are not."""
    s = str(s).replace("â€“", "-").replace("â€”", "-").replace("â†’", "->").replace("â€¦", "...")
    return s.encode("latin-1", "replace").decode("latin-1")


class _PDF(FPDF):
    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, _t("MobiPhysio - single-camera physiotherapy assessment. "
                           "This score supports, and does not replace, a physiotherapist's judgement."),
                  align="C")


def build(exercise_id, score, details, created=None, video_name=None, keyframes=()):
    """Returns the PDF as bytes."""
    ex = EXERCISES[exercise_id]
    created = created or time.time()
    label, meaning = score_meaning(score)
    mae = ex.reference["MAE"]

    pdf = _PDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    w = pdf.w - 32

    # header band
    pdf.set_fill_color(*NIGHT)
    pdf.rect(0, 0, pdf.w, 34, "F")
    pdf.set_xy(16, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 8, "MobiPhysio assessment report")
    pdf.set_xy(16, 19)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(185, 182, 227)
    pdf.cell(0, 6, _t(datetime.fromtimestamp(created).strftime("%d %B %Y, %H:%M")))

    # exercise + score
    pdf.set_xy(16, 44)
    pdf.set_text_color(*MUTED)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "EXERCISE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, _t(ex.name), new_x="LMARGIN", new_y="NEXT")

    y = pdf.get_y() + 4
    box_w = 58
    pdf.set_fill_color(240, 253, 250)
    pdf.set_draw_color(*LINE)
    pdf.rect(16, y, box_w, 40, "DF")
    pdf.set_xy(16, y + 5)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(box_w, 5, "SCORE", align="C")
    pdf.set_xy(16, y + 11)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*TEAL)
    pdf.cell(box_w, 14, f"{score:.2f}", align="C")
    pdf.set_xy(16, y + 27)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*BODY)
    pdf.cell(box_w, 5, "out of 100", align="C")

    x2 = 16 + box_w + 8
    pdf.set_xy(x2, y + 2)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, _t(f"What it means: {label}"), new_x="LEFT", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*BODY)
    pdf.multi_cell(w - box_w - 8, 5, _t(
        f"{meaning} The score runs from 0 to 100; higher is better. On the test videos the model "
        f"for this exercise was off by about {mae:.1f} points on average, so treat small changes "
        f"between sessions with care. Rough guide: 80-100 good, 50-79 fair, below 50 needs work."),
        align="L", new_x="LEFT", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), y + 40) + 8)

    # details table
    rows = [("Model", model_combo(ex)),
            ("Pipeline", f"YOLO26 2D keypoints -> KTPFormer 3D lift -> {ex.encoder} encoder "
                         f"({ex.modality.upper()} keypoints) -> {ex.regressor} regressor"),
            ("Expected error", f"+/-{mae:.2f} points (test MAE)")]
    if video_name:
        rows.append(("Video file", video_name))
    skip = {"model", "expected error"}
    rows += [(k, v) for k, v in (details or {}).items() if k.lower() not in skip]

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, "Details", new_x="LMARGIN", new_y="NEXT")
    for k, v in rows:
        pdf.set_draw_color(*LINE)
        pdf.line(16, pdf.get_y(), 16 + w, pdf.get_y())
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*MUTED)
        y0 = pdf.get_y()
        pdf.set_xy(16, y0 + 1.5)
        pdf.cell(42, 5, _t(k))
        pdf.set_xy(58, y0 + 1.5)
        pdf.set_text_color(*INK)
        pdf.multi_cell(w - 42, 5, _t(v), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(pdf.get_y() + 1.5)

    # key frames
    if keyframes:
        pdf.ln(5)
        img_w = (w - 8) / 2
        img_h = img_w * 0.62
        # keep all key frames together: start a new page if they do not fit under the table
        if pdf.get_y() + 14 + len(keyframes) * (img_h + 5) > pdf.h - 18:
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*INK)
        pdf.cell(0, 7, "Key frames", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(img_w + 8, 5, "Input video")
        pdf.cell(img_w, 5, "Skeleton output", new_x="LMARGIN", new_y="NEXT")
        for inp, skel in keyframes:
            if pdf.get_y() + img_h + 4 > pdf.h - 18:
                pdf.add_page()
            y0 = pdf.get_y() + 1
            for x, path in ((16, inp), (16 + img_w + 8, skel)):
                pdf.set_fill_color(241, 244, 246)
                pdf.rect(x, y0, img_w, img_h, "F")
                pdf.image(str(path), x=x, y=y0, w=img_w, h=img_h, keep_aspect_ratio=True)
            pdf.set_y(y0 + img_h + 4)

    return bytes(pdf.output())
