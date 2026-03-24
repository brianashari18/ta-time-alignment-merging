import pandas as pd
import os
import glob
import re


def normalize_title(text: str) -> str:
    """Normalize a string for comparison: lowercase, remove spaces/special chars."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def track_id_to_title_key(track_id: str) -> str:
    """
    Convert track_id (e.g. 'vierratale-jadi_yang_kuinginkan') to a normalized
    key for matching against song titles (e.g. 'Jadi Yang Ku Inginkan').
    Strips the artist prefix before the first '-', then normalizes the rest.
    """
    parts = track_id.split("-", 1)  # split on FIRST hyphen only
    song_part = parts[1] if len(parts) > 1 else parts[0]
    return normalize_title(song_part)


def merge_chords_alignment(chords_path: str, alignment_path: str, output_path: str):
    """
    Merge a *_cleaned_chords.csv with a *_clean_alignment.csv.

    Strategy:
    - Group chords by (title, artist) → each group is 1 song.
    - Normalize group title → match to the corresponding track_id rows in alignment.
    - Assign start_time / end_time in order (1st chord gets seq_order=1 timing, etc.)
    - If chord count != alignment rows for that song, print a warning and skip times.
    """
    chords_df = pd.read_csv(chords_path)
    align_df = pd.read_csv(alignment_path)

    # Strip whitespace from time columns that may have leading spaces
    for col in ["start_time", "end_time"]:
        if col in align_df.columns:
            align_df[col] = align_df[col].astype(str).str.strip()

    align_df["start_time"] = pd.to_numeric(align_df["start_time"], errors="coerce")
    align_df["end_time"] = pd.to_numeric(align_df["end_time"], errors="coerce")

    # Build lookup: normalized_title_key → sorted alignment rows
    align_grouped = {}
    for track_id, group in align_df.groupby("track_id"):
        key = track_id_to_title_key(track_id)
        # Sort by seq_order to guarantee correct ordering
        align_grouped[key] = group.sort_values("seq_order").reset_index(drop=True)

    # Ensure output time columns exist
    chords_df["start_time"] = chords_df.get("start_time", pd.Series(dtype=float))
    chords_df["end_time"] = chords_df.get("end_time", pd.Series(dtype=float))

    matched_songs = set()
    unmatched_songs = set()

    # Process chord rows in groups of (title, artist)
    updated_rows = []
    for (title, artist), group in chords_df.groupby(
        ["title", "artist"], sort=False
    ):
        key = normalize_title(title)
        group = group.copy().reset_index(drop=True)

        if key in align_grouped:
            align_rows = align_grouped[key]
            chord_count = len(group)
            align_count = len(align_rows)

            if chord_count == align_count:
                group["start_time"] = align_rows["start_time"].values
                group["end_time"] = align_rows["end_time"].values
                matched_songs.add(title)
            else:
                print(
                    f"[WARNING] '{title}': chord count ({chord_count}) != "
                    f"alignment count ({align_count}). Skipping time assignment."
                )
                unmatched_songs.add(title)
        else:
            print(f"[WARNING] No alignment found for song: '{title}' (key='{key}')")
            unmatched_songs.add(title)

        updated_rows.append(group)

    result_df = pd.concat(updated_rows, ignore_index=True)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_df.to_csv(output_path, index=False)

    print(f"\n✅ Merged output saved to: {output_path}")
    print(f"   Songs merged successfully : {len(matched_songs)}")
    if unmatched_songs:
        print(f"   Songs with issues         : {sorted(unmatched_songs)}")
    return result_df


def find_pairs(input_dir: str):
    """
    Auto-detect pairs of (*_cleaned_chords.csv, *_clean_alignment.csv) in input_dir.
    Pairs are matched by their common artist prefix (the part before the suffix).
    """
    chord_files = glob.glob(os.path.join(input_dir, "*_cleaned_chords.csv"))
    align_files = glob.glob(os.path.join(input_dir, "*_clean_alignment.csv"))

    def get_prefix(path, suffix):
        return os.path.basename(path)[: -len(suffix)]

    chord_map = {get_prefix(f, "_cleaned_chords.csv"): f for f in chord_files}
    align_map = {get_prefix(f, "_clean_alignment.csv"): f for f in align_files}

    pairs = []
    for prefix in chord_map:
        if prefix in align_map:
            pairs.append((chord_map[prefix], align_map[prefix], prefix))
        else:
            print(f"[INFO] No alignment file found for chords prefix: '{prefix}'")

    return pairs


if __name__ == "__main__":
    INPUT_DIR = os.path.join(os.path.dirname(__file__), "input")
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

    pairs = find_pairs(INPUT_DIR)

    if not pairs:
        print("No matching file pairs found in the input directory.")
    else:
        for chords_path, alignment_path, prefix in pairs:
            print(f"\n{'='*60}")
            print(f"Processing: {prefix}")
            print(f"  Chords   : {os.path.basename(chords_path)}")
            print(f"  Alignment: {os.path.basename(alignment_path)}")
            output_path = os.path.join(OUTPUT_DIR, f"{prefix}_merged.csv")
            merge_chords_alignment(chords_path, alignment_path, output_path)
