import apsw
import sqlite_vec
from pathlib import Path

sentences = [
    "Capri-Sun is a brand of juice concentrate–based drinks manufactured by the German company Wild and regional licensees.",
    "George V was King of the United Kingdom and the British Dominions, and Emperor of India, from 6 May 1910 until his death in 1936.",
    "Alaqua Cox is a Native American (Menominee) actress.",
    "Shohei Ohtani is a Japanese professional baseball pitcher and designated hitter for the Los Angeles Dodgers of Major League Baseball.",
    "Tamarindo, also commonly known as agua de tamarindo, is a non-alcoholic beverage made of tamarind, sugar, and water.",
]

db = apsw.Connection("shortmem_db")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)

with db:
    for i, sentence in enumerate(sentences):
        db.execute("INSERT INTO sentences(id, sentence) VALUES(?, ?)", [i, sentence])