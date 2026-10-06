import math

import numpy as np

def similar(left, right, max_hash_distance=8, max_pixel_rmse=0.08):
    if left["sha256"] == right["sha256"]:
        return True
    if abs(math.log(left["aspect"] / right["aspect"])) > 0.03:
        return False
    distance = (int(left["dhash"], 16) ^ int(right["dhash"], 16)).bit_count()
    if distance > max_hash_distance:
        return False
    rmse = np.sqrt(np.mean((left["signature"] - right["signature"]) ** 2))
    return bool(rmse <= max_pixel_rmse)

def group_images(records, max_hash_distance=8, max_pixel_rmse=0.08):
    if not 0 <= max_hash_distance <= 64:
        raise ValueError("Hash distance must be between 0 and 64")
    if not 0 <= max_pixel_rmse <= 1:
        raise ValueError("Pixel RMSE must be between 0 and 1")
    groups = []
    for index, row in enumerate(records):
        # Compare with every image so loose matches do not join separate groups
        for group in groups:
            if all(similar(row, records[other], max_hash_distance, max_pixel_rmse)
                   for other in group):
                group.append(index)
                break
        else:
            groups.append([index])
    return groups

def quality_key(row):
    clipped_fraction = row["dark_fraction"] + row["bright_fraction"]
    return -row["sharpness"], clipped_fraction, row["file"]

def review_order(records, groups):
    rows = []
    # Rank by sharpness, then clipped pixels; filename breaks ties
    for number, group in enumerate(groups, 1):
        ordered = sorted(group, key=lambda index: quality_key(records[index]))
        for rank, index in enumerate(ordered, 1):
            row = records[index]
            rows.append({
                "group": number, "rank": rank, "file": row["file"],
                "width": row["width"], "height": row["height"],
                "sharpness": row["sharpness"], "mean_luma": row["mean_luma"],
                "dark_fraction": row["dark_fraction"],
                "bright_fraction": row["bright_fraction"],
                "sha256": row["sha256"], "dhash": row["dhash"],
            })
    return rows
