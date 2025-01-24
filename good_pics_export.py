"""Populate slideshow directory with favorite pictures"""

import argparse
from datetime import datetime
import getpass
import random
from subprocess import check_output

from pathlib3x import Path
from PIL import Image
import slugify

slugify.unicode = str

ERASE = "\x1b[2K"  # erase line
USER = getpass.getuser()
DEST_DIR = f"/home/{USER}/Dropbox/five-star-pics"


def get_pic_filenames(num_limit: int = 40000) -> list[Path]:
    """Get the filenames of num_limit five-star pics out of the Shotwell DB."""
    sql = (
        "SELECT filename FROM PhotoTable "
        "WHERE rating = 5 "
        "ORDER BY id, time_created, filename ASC;"
    )
    db_file = f"/home/{USER}/.local/share/shotwell/data/photo.db"
    cmd = f"sqlite3 {db_file} '{sql}'"

    out = check_output(cmd, shell=True)
    pic_filenames = [Path(str(p, "utf-8")) for p in out.splitlines()]
    if len(pic_filenames) > num_limit:
        pic_filenames = random.sample(pic_filenames, num_limit)
    return pic_filenames


def shrink_large(file: Path, pix_limit: int, skip_resize: bool) -> bool:
    """If image is too large, resize down and save in place."""
    if skip_resize:
        return False
    with Image.open(file.as_posix()) as img:
        num_pixels = img.height * img.width
        is_too_big = num_pixels > pix_limit
        if is_too_big:
            ratio = pix_limit / num_pixels
            new_size = (int(ratio * img.width), int(ratio * img.height))
            out = img.resize(new_size)
            out.save(file.as_posix())
    return is_too_big


def get_dest_filenames(orig_files: list, args: argparse.Namespace) -> list:
    """Generate a list of original -> destination filenames."""

    def _get_date_from_shotwell_directories(filename: Path) -> str:
        return "-".join(filename.parts[-4:-1])

    def _make_new_dir_if_needed(i: int) -> Path:
        """
        Determine which directory the i-th photo should go into, creating the
        directory if it doesn't already exist.
        """
        subdir_num = i // args.pics_per_subdir
        pic_dir = Path(DEST_DIR, f"subdir{subdir_num:02}")
        if not pic_dir.is_dir():
            pic_dir.mkdir()
        return pic_dir

    def _make_dest_name(orig: str, i: int) -> Path:
        """
        Make the destination location for the file, including its new directory
        and filename.
        """
        date = _get_date_from_shotwell_directories(orig)
        slug = slugify.slugify(Path(date, orig.stem).as_posix()) + orig.suffix.lower()
        dest = Path(_make_new_dir_if_needed(i), slug)
        return dest

    filenames = [(o, _make_dest_name(o, i)) for i, o in enumerate(orig_files)]
    return filenames


def copy_and_resize(pic_filenames: list[Path], args: argparse.Namespace) -> dict:
    """Copy new files into correct subdir, resize if necessary."""
    print(f"Processing {len(pic_filenames)} image files")

    counts = dict(already_there=0, copied=0, error=0, resized=[])
    orig_dest_filenames = get_dest_filenames(pic_filenames, args)

    per_left_old = -1

    for i, (orig, dest) in enumerate(orig_dest_filenames):
        try:
            if dest.exists():
                counts["already_there"] += 1
            else:
                orig.copy(dest)
                counts["copied"] += 1
        except FileNotFoundError as err:
            print(f"\ncouldn't copy {orig} {err}")
            counts["error"] += 1
            continue

        # Resize if required
        try:
            was_resized = shrink_large(dest, args.PIX_LIMIT, args.RESIZE_SKIP)

            if was_resized:
                suffix = "(resizing)"
                counts["resized"].append(orig)
            else:
                suffix = ""

            # print a status line every 1 percent or if a resize has happened (they're slow):
            per_left = 100 - (100 * i // len(pic_filenames))  # int percentage [0-100]
            update_status_to_user = per_left != per_left_old
            if was_resized or update_status_to_user:
                print(
                    f"{ERASE}"
                    f"{per_left}% remaining "
                    f"(image {i}/{len(pic_filenames)}) "
                    f"{orig} {suffix}",
                    end="\r",
                )
                per_left_old = per_left
        except OSError as err:
            print(f"\ncouldn't resize {i} {orig} {err}")

    return counts


def parse_args():
    """Parse the (very simple) args for this script"""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--clear-all",
        dest="CLEAR_ALL_PHOTOS",
        default=False,
        action="store_true",
        help="Delete all images first (start fresh).",
    )
    parser.add_argument(
        "--resize-skip",
        dest="RESIZE_SKIP",
        default=False,
        action="store_true",
        help="Skip doing the resize (speeds up the run).",
    )
    parser.add_argument(
        "--max-pix-count",
        dest="PIX_LIMIT",
        default=1900000,
        help="Maximum number of pixels in output images.",
    )
    parser.add_argument(
        "--pics-per-subdir",
        dest="pics_per_subdir",
        default=1024,
        help="Maximum number of files in output directories.",
    )
    args = parser.parse_args()
    return args


def main():
    """Export good pics"""
    time_start = datetime.now()
    args = parse_args()

    if args.CLEAR_ALL_PHOTOS:
        # Erase contents of DEST_DIR
        print("clearing")
        dest_dir = Path(DEST_DIR)
        dest_dir.rmtree()
        dest_dir.mkdir()

    # Get the list of pics and copy:
    pic_filenames = get_pic_filenames()
    counts = copy_and_resize(pic_filenames, args)

    time_end = datetime.now()

    # Display report
    print(
        f"{ERASE}Processing complete: {counts['copied']} "
        f"new image{'' if counts['copied'] == 1 else 's'}, "
        f"{len(counts['resized'])} resized, "
        f"{counts['already_there']} already there, "
        f"{int((time_end - time_start).total_seconds())} seconds elapsed."
    )


if __name__ == "__main__":
    main()
