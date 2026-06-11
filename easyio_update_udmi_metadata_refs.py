#!/usr/bin/env python3
"""
Python script to extract data mapping paths from EasyIO .tgz backups
and update or add the corresponding 'ref' fields in UDMI device metadata.json files.
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import tarfile
from typing import Dict, Optional


def extract_point_path(data) -> Optional[str]:
    """
    Recursively searches for the 'path' key inside a point dictionary.
    """
    if isinstance(data, dict):
        if "path" in data and isinstance(data["path"], str):
            return data["path"]
        for _, v in data.items():
            res = extract_point_path(v)
            if res is not None:
                return res
    return None


def extract_device_points_mappings(mapping_data: dict) -> Dict[str, Dict[str, str]]:
    """
    Parses data_mapping.json content and returns a dictionary mapping
    device_id -> { point_name -> ref_path }.
    """
    device_mappings: Dict[str, Dict[str, str]] = {}

    broker_list = mapping_data.get("brokerList", [])
    if not isinstance(broker_list, list):
        return device_mappings

    for broker in broker_list:
        if not isinstance(broker, dict):
            continue

        broker_config = broker.get("config", {})
        device_id_from_config = broker_config.get("device_id")

        topic_list = broker.get("topicList", [])
        if not isinstance(topic_list, list):
            continue

        for topic in topic_list:
            if not isinstance(topic, dict):
                continue

            data_mapping = topic.get("dataMapping", {})
            if not isinstance(data_mapping, dict):
                continue

            for key, val in data_mapping.items():
                if isinstance(val, dict) and "points" in val:
                    dev_id = (
                        key
                        if key not in ["topic", "state", "device"]
                        else device_id_from_config
                    )
                    if not dev_id:
                        dev_id = device_id_from_config

                    if not dev_id:
                        continue

                    if dev_id not in device_mappings:
                        device_mappings[dev_id] = {}

                    points_dict = val["points"]
                    if not isinstance(points_dict, dict):
                        continue

                    for point_name, point_info in points_dict.items():
                        ref_path = extract_point_path(point_info)
                        if ref_path:
                            device_mappings[dev_id][point_name] = ref_path

    return device_mappings


def extract_mappings_from_tgz(
    tgz_path: str, verbose: bool = False
) -> Dict[str, Dict[str, str]]:
    """
    Opens a .tgz archive, searches for cpt/plugins/DataServiceConfig/data_mapping.json,
    and returns the extracted device point mappings.
    """
    device_mappings: Dict[str, Dict[str, str]] = {}
    try:
        with tarfile.open(tgz_path, "r:*") as tar:
            members = tar.getmembers()
            target_suffix = "cpt/plugins/DataServiceConfig/data_mapping.json"
            mapping_members = [m for m in members if m.path.endswith(target_suffix)]

            for member in mapping_members:
                if verbose:
                    print(f"   Found mapping file in archive: {member.path}")
                f = tar.extractfile(member)
                if not f:
                    continue
                try:
                    content = f.read().decode("utf-8")
                    mapping_data = json.loads(content)
                except Exception as e:
                    print(f"   Error parsing JSON in {member.path}: {e}", file=sys.stderr)
                    continue

                extracted = extract_device_points_mappings(mapping_data)
                for dev_id, pm in extracted.items():
                    if dev_id not in device_mappings:
                        device_mappings[dev_id] = {}
                    device_mappings[dev_id].update(pm)

    except Exception as e:
        print(f"  Error opening archive {tgz_path}: {e}", file=sys.stderr)

    return device_mappings


def update_device_metadata(
    udmi_devices_dir: str,
    device_id: str,
    point_map: Dict[str, str],
    dry_run: bool = False,
    backup: bool = False,
    operation_timestamp: Optional[str] = None,
    verbose: bool = False,
) -> int:
    """
    Updates the metadata.json file for a specific device,
    substituting or adding the 'ref' field for mapped points.
    Returns the number of points modified.
    """
    metadata_path = os.path.join(udmi_devices_dir, device_id, "metadata.json")
    if not os.path.isfile(metadata_path):
        if verbose:
            print(f"   Warning: Device metadata file not found at {metadata_path}")
        return 0

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        print(
            f"   Error reading/parsing metadata file {metadata_path}: {e}", file=sys.stderr
        )
        return 0

    if not isinstance(meta, dict):
        print(
            f"   Error: Metadata in {metadata_path} is not a JSON dictionary.",
            file=sys.stderr,
        )
        return 0

    # Ensure there is a pointset/points hierarchy
    if "pointset" not in meta or not isinstance(meta["pointset"], dict):
        meta["pointset"] = {}
    if "points" not in meta["pointset"] or not isinstance(
        meta["pointset"]["points"], dict
    ):
        meta["pointset"]["points"] = {}

    points_dict = meta["pointset"]["points"]
    updated_count = 0

    for point_name, ref_path in point_map.items():
        if point_name not in points_dict or not isinstance(
            points_dict[point_name], dict
        ):
            points_dict[point_name] = {}

        current_ref = points_dict[point_name].get("ref")
        if current_ref != ref_path:
            if verbose:
                action = "Updating" if current_ref else "Adding"
                print(
                    f"    {action} point '{point_name}' ref: '{current_ref}' -> '{ref_path}'"
                )
            points_dict[point_name]["ref"] = ref_path
            updated_count += 1
        else:
            if verbose:
                print(f"    Point '{point_name}' already has correct ref '{ref_path}'")

    if updated_count > 0:
        if backup:
            backup_path = f"{metadata_path}.{operation_timestamp}.bak.json"
            if dry_run:
                if verbose:
                    print(
                        f"   [Dry run] Would create backup of original metadata at {backup_path}"
                    )
            else:
                try:
                    shutil.copy2(metadata_path, backup_path)
                    if verbose:
                        print(f"   Created backup of original metadata at {backup_path}")
                except Exception as e:
                    print(
                        f"   Error creating backup {backup_path}: {e}", file=sys.stderr
                    )
                    return 0

        if not dry_run:
            try:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2)
                    f.write("\n")
                if verbose:
                    print(f"   Saved updated metadata to {metadata_path}")
            except Exception as e:
                print(f"   Error saving metadata to {metadata_path}: {e}", file=sys.stderr)

    return updated_count


def find_dated_project_folder(
    projects_dir: str, dated_folder_arg: Optional[str] = None
) -> str:
    """
    Finds the specific dated project folder, or defaults to the latest one.
    """
    if dated_folder_arg:
        if os.path.isdir(dated_folder_arg):
            return dated_folder_arg
        sub = os.path.join(projects_dir, dated_folder_arg)
        if os.path.isdir(sub):
            return sub
        raise FileNotFoundError(f"Project folder not found: {dated_folder_arg}")

    if not os.path.isdir(projects_dir):
        raise FileNotFoundError(f"Projects directory not found: {projects_dir}")

    entries = os.listdir(projects_dir)
    subdirs = [e for e in entries if os.path.isdir(os.path.join(projects_dir, e))]

    if not subdirs:
        raise FileNotFoundError(f"No dated project folders found inside {projects_dir}")

    subdirs.sort()
    latest = subdirs[-1]
    return os.path.join(projects_dir, latest)


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_projects_dir = os.path.join(
        script_dir, "batch_tools", "data", "projects"
    )
    default_udmi_dir = os.path.join(script_dir, "sites", "UK-LON-KGX1", "udmi", "devices")

    parser = argparse.ArgumentParser(
        description="Update UDMI device metadata.json point 'ref' fields from EasyIO backup archives."
    )
    parser.add_argument(
        "-p",
        "--projects-dir",
        default=default_projects_dir,
        help=f"Base directory containing dated project folders (default: {default_projects_dir})",
    )
    parser.add_argument(
        "-d",
        "--dated-folder",
        help="Specific dated folder name or path to process (if not specified, auto-picks the latest one)",
    )
    parser.add_argument(
        "-u",
        "--udmi-dir",
        default=default_udmi_dir,
        help=f"Path to UDMI devices folder hierarchy (default: {default_udmi_dir})",
    )
    parser.add_argument(
        "-b",
        "--backup",
        action="store_true",
        help="Create a timestamped backup (e.g. metadata.json.YYYYMMDD_HHMMSS.bak.json) before modifying original files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without modifying or backing up any files",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print detailed progress and inspection logs",
    )

    args = parser.parse_args()

    operation_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        dated_dir = find_dated_project_folder(
            args.projects_dir, args.dated_folder
        )
    except Exception as e:
        print(f"Error locating dated project folder: {e}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(args.udmi_dir):
        print(
            f"Error: UDMI devices directory not found at '{args.udmi_dir}'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Using Dated Project Folder: {dated_dir}")
    print(f"Using UDMI Devices Hierarchy: {args.udmi_dir}")
    if args.backup:
        print(f"BACKUP MODE ENABLED - Modified files will be backed up to: metadata.json.{operation_timestamp}.bak.json")
    if args.dry_run:
        print("DRY RUN MODE ENABLED - No files will be modified or backed up\n")
    else:
        print("")

    try:
        ip_entries = os.listdir(dated_dir)
    except Exception as e:
        print(f"Error listing {dated_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    total_devices_found = 0
    total_points_updated = 0

    for ip_entry in sorted(ip_entries):
        ip_dir = os.path.join(dated_dir, ip_entry)
        if not os.path.isdir(ip_dir) or ip_entry in ["logs"]:
            continue

        if args.verbose:
            print(f"Inspecting directory: {ip_entry}")

        tgz_files = [f for f in os.listdir(ip_dir) if f.endswith(".tgz")]
        for tgz in sorted(tgz_files):
            tgz_path = os.path.join(ip_dir, tgz)
            if args.verbose:
                print(f" Opening archive: {tgz}")

            mappings = extract_mappings_from_tgz(tgz_path, verbose=args.verbose)
            if not mappings:
                continue

            for device_id, point_map in mappings.items():
                total_devices_found += 1
                if args.verbose:
                    print(
                        f"  Updating metadata for device: '{device_id}' ({len(point_map)} points mapped)"
                    )
                updated = update_device_metadata(
                    args.udmi_dir,
                    device_id,
                    point_map,
                    dry_run=args.dry_run,
                    backup=args.backup,
                    operation_timestamp=operation_timestamp,
                    verbose=args.verbose,
                )
                total_points_updated += updated

    print(
        f"\nCompleted! Processed {total_devices_found} device mapping(s), updated/added {total_points_updated} point ref(s)."
    )


if __name__ == "__main__":
    main()
